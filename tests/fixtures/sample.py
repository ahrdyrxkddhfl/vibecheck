"""파서·청커 테스트용 최소 예제.

클래스 소속 메서드(Auth.login)와 최상위 함수(helper)를 함께 담아
walk()가 parent를 올바로 채우는지 확인한다. import os는
extract_imports() 검증용이다.
"""

import os

class Auth:
    def login(self, user_id):
        return True

    def logout(self):
        pass

def helper(x):
    return x * 2