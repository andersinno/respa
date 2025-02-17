def get_user_auth_backend(request):
    authentication_backend = request.auth.get("backend")
    return authentication_backend
