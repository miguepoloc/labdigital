"""Política de contraseñas (plan §Autenticación): mínimo 10 caracteres, máximo 256 (Argon2
con entradas enormes es un vector de DoS) y fuera de una lista corta de contraseñas
comunes. Se comprueba al registrarse, restablecer y cambiar la contraseña."""

from backend.commons.domain import business_rules, exceptions

MIN_LENGTH = 10
MAX_LENGTH = 256

# Lista corta (las más frecuentes en filtraciones públicas con ≥ 10 caracteres, más
# variantes locales obvias). No pretende ser exhaustiva.
_COMMON_PASSWORDS = frozenset(
    {
        "1234567890",
        "12345678910",
        "123456789a",
        "0123456789",
        "0987654321",
        "1111111111",
        "1q2w3e4r5t",
        "qwertyuiop",
        "qwerty1234",
        "qwerty123456",
        "password12",
        "password123",
        "password1234",
        "contraseña",
        "contraseña1",
        "contraseña123",
        "contrasena",
        "contrasena123",
        "iloveyou12",
        "abcdefghij",
        "abc1234567",
        "aaaaaaaaaa",
        "asdfghjkl1",
        "zxcvbnm123",
        "unimagdalena",
        "unimagdalena1",
        "unimagdalena123",
        "labdigital",
        "labdigital1",
        "labdigital123",
        "gideam1234",
        "santamarta",
        "santamarta1",
        "colombia123",
        "colombia1234",
        "basys31234",
        "fpga123456",
    }
)


class PasswordPolicy(business_rules.BusinessRule):
    def __init__(self, plaintext: str) -> None:
        self._plaintext = plaintext
        self._reason = self._evaluate()

    def _evaluate(self) -> str | None:
        if len(self._plaintext) < MIN_LENGTH:
            return "too_short"
        if len(self._plaintext) > MAX_LENGTH:
            return "too_long"
        if self._plaintext.strip().lower() in _COMMON_PASSWORDS:
            return "too_common"
        if len(set(self._plaintext)) < 3:
            return "too_common"
        return None

    def is_broken(self) -> bool:
        return self._reason is not None

    def message(self) -> str:
        return {
            "too_short": f"La contraseña debe tener al menos {MIN_LENGTH} caracteres.",
            "too_long": f"La contraseña no puede superar {MAX_LENGTH} caracteres.",
            "too_common": "Esa contraseña es demasiado común. Elige otra.",
        }.get(self._reason or "", "Contraseña no válida.")

    def check(self) -> None:
        if self.is_broken():
            raise exceptions.ValidationError(
                self.message(),
                code="validation_error",
                details={"field": "password", "reason": self._reason},
            )
