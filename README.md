
## Google OAuth / Django Allauth

Google social login is configured through environment variables. Add these locally or in your deployment provider:

```bash
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret
```

Register the callback URL in Google Cloud Console, for example:

```text
http://127.0.0.1:8000/accounts/google/login/callback/
https://your-domain/accounts/google/login/callback/
```
