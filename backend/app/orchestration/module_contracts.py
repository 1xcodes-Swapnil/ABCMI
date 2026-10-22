"""Validate the existing ACE module envelope before accepting task completion."""
import json
import math


def validate_module_result(output, *, capability, meeting_id, request_id, task_id,
                           correlation_id=None, require_json=False):
    if not isinstance(output, dict) or output.get("status") != "SUCCESS":
        raise ValueError(f"Module {capability} did not return a SUCCESS envelope")
    if output.get("capability") != capability:
        raise ValueError(f"Module {capability} returned a different capability")
    if not isinstance(output.get("result_data"), dict):
        raise ValueError(f"Module {capability} must return an object in result_data")
    score = output.get("confidence_score")
    if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))
                              or not math.isfinite(score) or not 0 <= score <= 1):
        raise ValueError(f"Module {capability} returned invalid confidence")
    identities = {"meeting_id": str(meeting_id), "request_id": str(request_id),
                  "task_id": str(task_id), "correlation_id": correlation_id}
    for key, expected in identities.items():
        if output.get(key) is not None and str(output[key]) != str(expected):
            raise ValueError(f"Module {capability} returned a different {key}")
    data_meeting = output["result_data"].get("meeting_id")
    if data_meeting is not None and str(data_meeting) != str(meeting_id):
        raise ValueError(f"Module {capability} payload belongs to a different meeting")
    result = {**output, **identities}
    if require_json:
        try:
            json.dumps(result, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Module {capability} returned a non-JSON-safe envelope") from exc
    return result
