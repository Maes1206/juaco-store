SELECT email, is_active, is_staff, is_superuser
FROM auth_user
WHERE lower(email) IN (
    'emersonmanquillo@gmail.com',
    'u20242226877@usco.edu.co'
)
ORDER BY lower(email);
