"""Mocks des outils externes de l'agent AI Education.

Chaque mock simule un service réel (API de cours, API de progression)
avec un scénario : success | error_500 | timeout | empty.
Aucun appel réseau : les tests sont rapides, déterministes et gratuits.
"""

COURSES = {
    "fractions": {"id": "C-MATH-01", "title": "Les fractions",
                  "summary": "Une fraction représente une part d'un tout : numérateur / dénominateur.",
                  "level": "college"},
    "equations": {"id": "C-MATH-02", "title": "Équations du premier degré",
                  "summary": "Pour résoudre ax + b = 0, on isole x : x = -b / a.",
                  "level": "college"},
    "python": {"id": "C-INF-01", "title": "Introduction à Python",
               "summary": "Python est un langage lisible : variables, boucles, fonctions.",
               "level": "lycee"},
    "photosynthese": {"id": "C-SVT-01", "title": "La photosynthèse",
                      "summary": "Les plantes transforment lumière, eau et CO2 en glucose et en O2.",
                      "level": "college"},
    "grammaire": {"id": "C-FR-01", "title": "Les accords en grammaire",
                  "summary": "Le participe passé s'accorde selon l'auxiliaire et le COD.",
                  "level": "college"},
}

QUIZ_BANK = {
    "fractions": [
        {"q": "Que vaut 1/2 + 1/4 ?", "choices": ["3/4", "2/6", "1/8"], "answer_index": 0},
        {"q": "Dans 3/5, quel est le dénominateur ?", "choices": ["3", "5", "8"], "answer_index": 1},
    ],
    "equations": [
        {"q": "Résoudre 2x + 4 = 0", "choices": ["x = 2", "x = -2", "x = 4"], "answer_index": 1},
        {"q": "Résoudre x - 5 = 0", "choices": ["x = 5", "x = -5", "x = 0"], "answer_index": 0},
    ],
    "python": [
        {"q": "Quel mot-clé définit une fonction ?", "choices": ["func", "def", "lambda"], "answer_index": 1},
        {"q": "len([1, 2, 3]) retourne :", "choices": ["2", "3", "4"], "answer_index": 1},
    ],
    "photosynthese": [
        {"q": "Quel gaz est rejeté ?", "choices": ["CO2", "O2", "N2"], "answer_index": 1},
    ],
    "grammaire": [
        {"q": "« Elle est partie » : le participe s'accorde avec…", "choices": ["l'auxiliaire être", "le COD", "rien"], "answer_index": 0},
    ],
}

PROGRESS = {
    "S001": {"completed": ["fractions"], "score": 72},
    "S002": {"completed": ["python", "equations"], "score": 88},
    "S003": {"completed": [], "score": 0},
}


class ToolError(Exception):
    """Erreur HTTP 500 simulée."""


class ToolTimeout(Exception):
    """Timeout simulé."""


class MockCourseAPI:
    def __init__(self, scenario="success"):
        self.scenario = scenario
        self.calls = 0

    def get_course(self, topic):
        self.calls += 1
        if self.scenario == "error_500":
            raise ToolError("500 Internal Server Error")
        if self.scenario == "timeout":
            raise ToolTimeout("timeout après 5 s")
        if self.scenario == "empty":
            return None
        return COURSES.get(topic)

    def get_quiz(self, topic):
        if self.scenario in ("error_500", "timeout"):
            return []
        return QUIZ_BANK.get(topic, [])


class MockProgressAPI:
    def __init__(self, scenario="success"):
        self.scenario = scenario
        self.calls = 0

    def get_progress(self, student_id):
        self.calls += 1
        if self.scenario == "error_500":
            raise ToolError("500 Internal Server Error")
        if self.scenario == "timeout":
            raise ToolTimeout("timeout après 5 s")
        return PROGRESS.get(student_id)


class FlakyCourseAPI(MockCourseAPI):
    """Échoue au 1er appel puis réussit : valide la logique de retry."""

    def get_course(self, topic):
        self.calls += 1
        if self.calls == 1:
            raise ToolTimeout("timeout après 5 s")
        return COURSES.get(topic)
