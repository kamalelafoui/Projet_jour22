"""Agent AI Education : tuteur pédagogique testable et déterministe.

Usage :  python main.py "Explique-moi les fractions" --student S001 --level college
"""
import argparse
import json
import re
import unicodedata

from mocks import MockCourseAPI, MockProgressAPI, ToolError, ToolTimeout

LEVELS = {"primaire", "college", "lycee", "universite"}
STUDENT_RE = re.compile(r"^S\d{3}$")
MAX_QUESTION = 500
MAX_RETRIES = 1

REQUIRED_KEYS = {"status": str, "intent": str, "answer": str, "level": str,
                 "quiz": list, "sources": list, "trace": list}
STATUSES = {"ok", "refused", "error", "degraded"}

INJECTION = ["ignore tes instructions", "ignore previous", "oublie tes regles",
             "system prompt", "prompt systeme"]
CHEATING = ["reponses de l'examen", "reponses de l examen", "corrige de l'examen",
            "triche", "faire mon examen a ma place", "sujet d'examen secret"]
OFF_TOPIC = ["bitcoin", "pari sportif", "arme", "pirater", "hack"]


def norm(text):
    """Minuscule + suppression des accents pour comparer les mots-clés."""
    t = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


class EducationAgent:
    def __init__(self, course_api=None, progress_api=None):
        self.course_api = course_api or MockCourseAPI()
        self.progress_api = progress_api or MockProgressAPI()

    # ---------- helpers ----------
    @staticmethod
    def _resp(status, intent, answer, level="", quiz=None, sources=None, trace=None):
        return {"status": status, "intent": intent, "answer": answer, "level": level,
                "quiz": quiz or [], "sources": sources or [], "trace": trace or []}

    @staticmethod
    def validate_response(resp):
        """Test de format : retourne la liste des erreurs de schéma."""
        errors = []
        if not isinstance(resp, dict):
            return ["la réponse n'est pas un objet JSON"]
        for key, typ in REQUIRED_KEYS.items():
            if key not in resp:
                errors.append(f"champ manquant : {key}")
            elif not isinstance(resp[key], typ):
                errors.append(f"type invalide pour {key}")
        if resp.get("status") not in STATUSES:
            errors.append("status inconnu")
        for q in resp.get("quiz", []):
            if not {"q", "choices", "answer_index"} <= set(q):
                errors.append("question de quiz incomplète")
            elif not 0 <= q["answer_index"] < len(q["choices"]):
                errors.append("answer_index hors limites")
        return errors

    @staticmethod
    def detect_intent(question):
        q = norm(question)
        if any(w in q for w in ("quiz", "exercice", "teste-moi", "entraine")):
            return "quiz"
        if any(w in q for w in ("progres", "score", "avancement")):
            return "progress"
        return "explain"

    @staticmethod
    def detect_topic(question):
        q = norm(question)
        for topic in ("fractions", "equations", "python", "photosynthese", "grammaire"):
            if topic[:-1] in q:
                return topic
        return None

    def _call_with_retry(self, fn, *args, trace=None):
        last = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                result = fn(*args)
                if trace is not None:
                    trace.append({"tool": fn.__name__, "attempt": attempt + 1, "ok": True})
                return result
            except (ToolError, ToolTimeout) as exc:
                last = exc
                if trace is not None:
                    trace.append({"tool": fn.__name__, "attempt": attempt + 1,
                                  "ok": False, "error": type(exc).__name__})
        raise last

    # ---------- point d'entrée ----------
    def handle(self, request):
        # 1. validation des entrées (robustesse)
        if not isinstance(request, dict):
            return self._resp("error", "invalid", "Requête invalide : un objet JSON est attendu.")
        question = request.get("question")
        student = request.get("student_id", "")
        level = request.get("level", "college")
        if not isinstance(question, str) or not question.strip():
            return self._resp("error", "invalid", "La question est vide.", level if level in LEVELS else "")
        if len(question) > MAX_QUESTION:
            return self._resp("error", "invalid", "La question dépasse 500 caractères.")
        if level not in LEVELS:
            return self._resp("error", "invalid", f"Niveau inconnu : {level}.")
        if not isinstance(student, str) or not STUDENT_RE.match(student):
            return self._resp("error", "invalid", "Identifiant élève invalide (format S123).", level)

        # 2. policy (règles métier)
        q = norm(question)
        if any(p in q for p in INJECTION):
            return self._resp("refused", "policy", "Je ne peux pas modifier mes instructions.", level)
        if any(p in q for p in CHEATING):
            return self._resp("refused", "policy",
                              "Je ne peux pas aider à tricher, mais je peux t'expliquer le cours.", level)
        if any(p in q for p in OFF_TOPIC):
            return self._resp("refused", "policy",
                              "Cette demande sort du cadre éducatif.", level)
        other = request.get("other_student_id")
        if other and other != student:
            return self._resp("refused", "policy",
                              "Accès refusé : la progression d'un autre élève est confidentielle.", level)

        # 3. routage
        intent = self.detect_intent(question)
        trace = []
        if intent == "progress":
            return self._progress(student, level, trace)
        topic = self.detect_topic(question)
        if topic is None:
            return self._resp("ok", intent,
                              "Je n'ai pas encore ce sujet. Essaie : fractions, équations, Python, "
                              "photosynthèse ou grammaire.", level, trace=trace)
        return self._course(intent, topic, level, trace)

    def _course(self, intent, topic, level, trace):
        try:
            course = self._call_with_retry(self.course_api.get_course, topic, trace=trace)
        except (ToolError, ToolTimeout):
            return self._resp("degraded", intent,
                              "Le service de cours est indisponible. Réessaie dans quelques minutes.",
                              level, trace=trace)
        if course is None:
            return self._resp("ok", intent, "Aucun cours trouvé pour ce sujet.", level, trace=trace)
        quiz = self.course_api.get_quiz(topic) if intent == "quiz" else []
        answer = f"{course['title']} : {course['summary']}"
        if intent == "quiz":
            answer = f"Voici un quiz sur « {course['title']} »."
        return self._resp("ok", intent, answer, level, quiz, [course["id"]], trace)

    def _progress(self, student, level, trace):
        try:
            data = self._call_with_retry(self.progress_api.get_progress, student, trace=trace)
        except (ToolError, ToolTimeout):
            return self._resp("degraded", "progress",
                              "Le suivi de progression est indisponible pour le moment.", level, trace=trace)
        if data is None:
            return self._resp("ok", "progress", "Aucune progression enregistrée.", level, trace=trace)
        done = ", ".join(data["completed"]) or "aucun cours"
        return self._resp("ok", "progress",
                          f"Score moyen : {data['score']}/100. Cours terminés : {done}.",
                          level, sources=[student], trace=trace)


def build_parser():
    ap = argparse.ArgumentParser(
        description="Agent AI Education (outils mockés). Sans question : mode interactif.")
    ap.add_argument("question", nargs="?", help="question de l'élève")
    ap.add_argument("--student", default="S001", help="identifiant élève (format S123)")
    ap.add_argument("--level", default="college", help="primaire | college | lycee | universite")
    ap.add_argument("--scenario", default="success",
                    choices=["success", "error_500", "timeout", "empty"], help="scénario de mock")
    ap.add_argument("--other-student", default="", help="simule la demande de progression d'un autre élève")
    ap.add_argument("--compact", action="store_true", help="JSON sur une seule ligne")
    return ap


def ask(agent, question, args):
    request = {"question": question, "student_id": args.student, "level": args.level}
    if args.other_student:
        request["other_student_id"] = args.other_student
    out = agent.handle(request)
    print(json.dumps(out, ensure_ascii=False, indent=None if args.compact else 2))
    return out


def main():
    args = build_parser().parse_args()
    agent = EducationAgent(MockCourseAPI(args.scenario), MockProgressAPI(args.scenario))
    if args.question:
        out = ask(agent, args.question, args)
        return 0 if out["status"] in ("ok", "refused") else 1
    print(f"AI Education — mode interactif (élève {args.student}, niveau {args.level}, "
          f"mock {args.scenario}). Ligne vide ou 'quit' pour sortir.")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if q.lower() in ("", "quit", "exit"):
            break
        ask(agent, q, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
