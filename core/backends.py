from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model() 

class MatriculaBackend(ModelBackend):
    """
    Backend de autenticação que permite login por Username, Matrícula, CPF ou E-mail.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            return None
            
        try:            
            query = Q(username__iexact=username) | \
                    Q(matricula__iexact=username) | \
                    Q(cpf__iexact=username) | \
                    Q(email__iexact=username)

            if username.isdigit():
                clean_username = str(int(username))
                
                paddings = [clean_username.zfill(i) for i in range(len(clean_username), 11)]
                
                query |= Q(matricula__in=paddings) | Q(username__in=paddings)

            user = UserModel.objects.filter(query).first()

        except UserModel.DoesNotExist:
            return None
        
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None

    def get_user(self, user_id):
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
    