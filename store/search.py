"""Motor de b\u00fasqueda unificada para el cat\u00e1logo y el blog."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from django.db.models import Q, QuerySet

from .models import BlogPost, Product


@dataclass(frozen=True)
class SearchQuery:
    """Representa una consulta limpia y comparable sin depender de acentos."""

    raw: str
    normalized: str
    tokens: tuple[str, ...]

    @classmethod
    def from_raw(cls, value: str | None) -> "SearchQuery":
        raw = " ".join((value or "").split())[:100]
        normalized = cls.normalize(raw)
        return cls(raw=raw, normalized=normalized, tokens=tuple(normalized.split()))

    @staticmethod
    def normalize(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(character for character in text if not unicodedata.combining(character))
        return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())

    @property
    def is_empty(self) -> bool:
        return not self.tokens

    def matches(self, value: Any) -> bool:
        normalized_value = self.normalize(value)
        return all(token in normalized_value for token in self.tokens)


@dataclass(frozen=True)
class SearchHit:
    """Resultado enriquecido para mostrar la coincidencia y sus subetiquetas."""

    item: Product | BlogPost
    score: int
    matched_tags: tuple[str, ...]


@dataclass(frozen=True)
class SearchResults:
    query: SearchQuery
    products: tuple[SearchHit, ...]
    posts: tuple[SearchHit, ...]

    @property
    def total(self) -> int:
        return len(self.products) + len(self.posts)


class UnifiedSearchService:
    """Busca y ordena productos y art\u00edculos con las mismas reglas de relevancia."""

    PRODUCT_FIELDS = ("name", "brand", "slug", "description", "tags")
    POST_FIELDS = ("title", "slug", "summary", "content", "tags", "category__name", "category__slug")
    RESULT_LIMIT = 12

    def search(self, raw_query: str | None) -> SearchResults:
        query = SearchQuery.from_raw(raw_query)
        if query.is_empty:
            return SearchResults(query=query, products=(), posts=())
        return SearchResults(
            query=query,
            products=tuple(self._search_products(query)),
            posts=tuple(self._search_posts(query)),
        )

    def _search_products(self, query: SearchQuery) -> list[SearchHit]:
        products = Product.objects.filter(is_active=True)
        candidates = self._database_candidates(products, self.PRODUCT_FIELDS, query)
        hits = self._rank(candidates, query, self._product_searchable_values)
        if not hits:
            hits = self._rank(products, query, self._product_searchable_values)
        return hits[: self.RESULT_LIMIT]

    def _search_posts(self, query: SearchQuery) -> list[SearchHit]:
        posts = BlogPost.objects.filter(is_published=True).select_related("category")
        candidates = self._database_candidates(posts, self.POST_FIELDS, query)
        hits = self._rank(candidates, query, self._post_searchable_values)
        if not hits:
            hits = self._rank(posts, query, self._post_searchable_values)
        return hits[: self.RESULT_LIMIT]

    @staticmethod
    def _database_candidates(queryset: QuerySet, fields: tuple[str, ...], query: SearchQuery) -> QuerySet:
        filters = Q()
        for token in query.tokens:
            token_filter = Q()
            for field in fields:
                token_filter |= Q(**{f"{field}__icontains": token})
            filters &= token_filter
        return queryset.filter(filters).distinct()

    def _rank(
        self,
        candidates: Iterable[Product | BlogPost],
        query: SearchQuery,
        value_getter,
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for candidate in candidates:
            fields, tags = value_getter(candidate)
            normalized_fields = [(weight, SearchQuery.normalize(value)) for weight, value in fields]
            searchable_text = " ".join(value for _, value in normalized_fields)
            if not all(token in searchable_text for token in query.tokens):
                continue
            score = self._score(normalized_fields, query)
            matched_tags = tuple(tag for tag in tags if query.matches(tag))
            if matched_tags:
                score += 80 * len(matched_tags)
            hits.append(SearchHit(item=candidate, score=score, matched_tags=matched_tags))
        return sorted(hits, key=lambda hit: (-hit.score, self._result_name(hit.item)))

    @staticmethod
    def _score(fields: list[tuple[int, str]], query: SearchQuery) -> int:
        score = 0
        for weight, value in fields:
            if not value:
                continue
            if value == query.normalized:
                score += weight * 50
            elif value.startswith(query.normalized):
                score += weight * 20
            elif query.normalized in value:
                score += weight * 10
            for token in query.tokens:
                if value == token:
                    score += weight * 12
                elif value.startswith(token):
                    score += weight * 5
                elif token in value:
                    score += weight * 2
        return score

    @staticmethod
    def _product_searchable_values(product: Product) -> tuple[list[tuple[int, Any]], list[str]]:
        tags = list(product.tags or [])
        return [
            (16, product.name),
            (12, product.brand),
            (10, " ".join(tags)),
            (8, product.slug),
            (4, product.description),
            (3, " ".join(product.sizes or [])),
        ], tags

    @staticmethod
    def _post_searchable_values(post: BlogPost) -> tuple[list[tuple[int, Any]], list[str]]:
        tags = list(post.tags or [])
        return [
            (16, post.title),
            (12, " ".join(tags)),
            (10, post.category.name),
            (8, post.slug),
            (6, post.summary),
            (2, post.content),
        ], tags

    @staticmethod
    def _result_name(item: Product | BlogPost) -> str:
        return SearchQuery.normalize(item.name if isinstance(item, Product) else item.title)
