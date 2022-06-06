from rest_framework_jwt.utils import jwt_decode_handler

def get_user_auth_backend(request):
    decoded_json_token = jwt_decode_handler(request.auth)
    authentication_backend = decoded_json_token.get("backend")
    return authentication_backend
