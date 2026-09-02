# Auth Testing Playbook — TALBROS

Admin: jbenterpriises01@gmail.com / Talbros@2026 (role admin)

## API
```
curl -c cookies.txt -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"jbenterpriises01@gmail.com","password":"Talbros@2026"}'
curl -b cookies.txt http://localhost:8001/api/auth/me
```
Login returns the user object and sets access_token + refresh_token cookies.
/me returns the same user using those cookies.
