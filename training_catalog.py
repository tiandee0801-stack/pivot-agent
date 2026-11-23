"""Preview-only basketball exercise definitions and compatible plan actions."""

import json
import math
import os
from functools import lru_cache
from pathlib import Path


CATALOG_FILE = Path(__file__).with_name("training_catalog.json")
SPACES = {"home", "gym", "court"}
MAX_ACTIONS = 32
METRIC_FIELDS = {
    "reps": ("reps", "sets", "weight"),
    "time": ("seconds", "sets"),
    "distance": ("distanceMeters", "seconds", "rounds", "sets"),
    "rounds": ("rounds", "seconds", "distanceMeters", "sets"),
}
METRIC_LIMITS = {"reps": 1000, "sets": 20, "seconds": 14400, "distanceMeters": 50000, "rounds": 1000}
PLAN_QUANTITY = {"reps": "reps", "time": "seconds", "distance": "distanceMeters", "rounds": "rounds"}


def enabled():
    return os.environ.get("PIVOT_CATALOG_PREVIEW") == "1" and not os.environ.get("PIVOT_PUBLIC_ORIGIN")


@lru_cache(maxsize=1)
def catalog():
    from video_engine.exercises import EXERCISES

    with CATALOG_FILE.open(encoding="utf-8") as stream:
        data = json.load(stream)
    exercises = [
        {**exercise, "videoSupported": bool(exercise.get("videoSupported") and exercise["id"] in EXERCISES)}
        for exercise in data["exercises"]
    ]
    return {**data, "reviewStatus": "pending", "preview": True, "exercises": exercises}


@lru_cache(maxsize=1)
def exercises_by_id():
    return {exercise["id"]: exercise for exercise in catalog()["exercises"]}


def _require_preview():
    from engine import RequestError

    if not enabled():
        raise RequestError("篮球动作库内容待审核，请在本地预览中体验。", "catalog_unavailable", 403)


def duration_seconds(exercise, quantity, sets, rest):
    # Repetition, distance and round estimates come from versioned draft
    # content. Rest is counted only between working sets.
    seconds_per_unit = 1 if exercise["metric"] == "time" else exercise["secondsPerUnit"]
    return math.ceil(quantity * sets * seconds_per_unit + max(sets - 1, 0) * rest)


def action_snapshot(exercise, quantity, sets, rest, optional=False):
    return {
        "exerciseId": exercise["id"], "exerciseName": exercise["name"], "metric": exercise["metric"],
        "quantity": quantity, "sets": sets, "restSeconds": rest, "optional": optional,
        "estimatedSeconds": duration_seconds(exercise, quantity, sets, rest),
    }


def plan_patch(body, previous):
    from engine import RequestError, integer, string

    if not {"actions", "templateId", "space"}.intersection(body):
        return {}
    _require_preview()
    if "space" in body:
        space = string(body, "space", 10)
        if space and space not in SPACES:
            raise RequestError("请选择居家、健身房或球场。")
    else:
        space = previous.get("space", "")
    if "actions" not in body:
        if "templateId" in body:
            raise RequestError("从模板保存计划时，请一并提交动作顺序。")
        return {"space": space}
    rows = body["actions"]
    if not isinstance(rows, list) or not 0 <= len(rows) <= MAX_ACTIONS:
        raise RequestError(f"一次计划最多保存 {MAX_ACTIONS} 项动作。")
    template_id = string(body, "templateId", 60) if "templateId" in body else previous.get("templateId", "")
    template = next((item for item in catalog()["templates"] if item["id"] == template_id), None)
    if template_id and template is None:
        raise RequestError("请选择动作库中的训练模板。")
    if ("space" not in body and template and len(template["space"]) == 1
            and (not space or template_id != previous.get("templateId"))):
        space = template["space"][0]
    if not rows:
        return {"actions": [], "templateId": "", "space": space, "catalogVersion": catalog()["version"]}
    optional_ids = {
        row["exerciseId"] for row in (template or {}).get("actions", []) if row.get("optional") is True
    }
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise RequestError("计划动作格式无效。")
        exercise = exercises_by_id().get(string(row, "exerciseId", 60, True))
        if exercise is None:
            raise RequestError("请选择已收录的动作。")
        metric_limit = METRIC_LIMITS[PLAN_QUANTITY[exercise["metric"]]]
        quantity = integer(row.get("quantity"), 1, metric_limit)
        sets = integer(row.get("sets"), 1, METRIC_LIMITS["sets"])
        rest = integer(row.get("restSeconds", 0), 0, 600)
        result.append(action_snapshot(exercise, quantity, sets, rest, exercise["id"] in optional_ids))
    return {"actions": result, "templateId": template_id, "space": space, "catalogVersion": catalog()["version"]}


def session_entries(body, previous, completion):
    from engine import RequestError, integer, string

    if "exerciseEntries" not in body:
        if completion == "not_done" and (previous or {}).get("exerciseEntries"):
            raise RequestError("标记为未训练前，请先清空实际动作记录。")
        return (previous or {}).get("exerciseEntries")
    _require_preview()
    rows = body["exerciseEntries"]
    if not isinstance(rows, list) or len(rows) > MAX_ACTIONS:
        raise RequestError(f"每次训练最多记录 {MAX_ACTIONS} 项动作。")
    if completion == "not_done":
        if rows:
            raise RequestError("未训练记录请清空实际动作。")
        return []
    if not rows:
        raise RequestError("请至少记录一项已做的动作。")
    results = []
    for row in rows:
        if not isinstance(row, dict):
            raise RequestError("实际动作格式无效。")
        exercise = exercises_by_id().get(string(row, "exerciseId", 60, True))
        if exercise is None:
            raise RequestError("请选择已收录的动作。")
        metric = exercise["metric"]
        allowed = METRIC_FIELDS[metric]
        if any(field in row and row[field] is not None and field not in allowed for field in METRIC_LIMITS.keys() | {"weight"}):
            raise RequestError(f"{exercise['name']} 的记录单位不匹配。")
        primary = allowed[0]
        entry = {
            "exerciseId": exercise["id"], "exerciseName": exercise["name"], "metric": metric,
            primary: integer(row.get(primary), 1, METRIC_LIMITS[primary]),
        }
        for field in allowed[1:]:
            value = row.get(field)
            if field == "sets" and metric == "reps":
                entry[field] = integer(value, 1, METRIC_LIMITS[field])
            elif field == "weight" and value is not None:
                if type(value) not in (int, float) or not 0 <= value <= 500:
                    raise RequestError("重量需要在 0–500 kg 范围内。")
                entry[field] = value
            elif value is not None:
                entry[field] = integer(value, 1, METRIC_LIMITS[field])
        results.append(entry)
    return results


def compatible_action(action, available, space, anchor, restrictions):
    """Preserve the original exercise first, then try explicit equivalent IDs."""
    index = exercises_by_id()
    original = index.get(action["exerciseId"])
    if original is None:
        return None, "unavailable"
    needs_anchor = False
    for exercise_id in [original["id"], *original.get("alternatives", [])]:
        replacement = index.get(exercise_id)
        if not replacement or replacement["goal"] != original["goal"] or replacement["metric"] != original["metric"]:
            continue
        if space not in replacement["space"] or not set(replacement["equipment"]) <= available:
            continue
        described = " ".join((replacement["name"], *replacement.get("aliases", []), replacement["goal"],
                              replacement["category"], *replacement["equipment"]))
        if any(term in described for term in restrictions):
            continue
        if replacement.get("anchorRequired") and anchor is not True:
            needs_anchor = needs_anchor or anchor is None
            continue
        return action_snapshot(replacement, action["quantity"], action["sets"], action.get("restSeconds", 0),
                               action.get("optional", False)), None
    return None, "anchor_missing" if needs_anchor else "unavailable"
