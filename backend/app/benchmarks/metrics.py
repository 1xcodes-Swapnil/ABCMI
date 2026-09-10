"""
Mathematical metric evaluation engine for ASR, Diarization, and Alignment.
Implements Word Error Rate (WER), Character Error Rate (CER), Diarization Error Rate (DER)
with Hungarian maximum matching and evaluation collar, and boundary alignment errors.
"""

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class BenchmarkMetrics:
    """Consolidated metric score container."""
    wer: Optional[float] = None
    cer: Optional[float] = None
    der: Optional[float] = None
    missed_speech_rate: Optional[float] = None
    false_alarm_rate: Optional[float] = None
    speaker_confusion_rate: Optional[float] = None
    mean_boundary_error_ms: Optional[float] = None
    median_boundary_error_ms: Optional[float] = None
    rtf: Optional[float] = None
    raw_counts: Dict[str, Any] = None


def normalize_text(text: str, remove_punctuation: bool = True) -> str:
    """Normalize text for consistent phonetic/lexical evaluation."""
    if not text:
        return ""
    text = text.strip().lower()
    if remove_punctuation:
        # Keep alphanumeric, whitespace, and non-ASCII Unicode characters (for Asian/Indic)
        text = re.sub(r"[^\w\s\u0400-\u04FF\u0600-\u06FF\u0900-\u097F\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]", " ", text)
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def calculate_wer(reference: str, hypothesis: str) -> Dict[str, Any]:
    """
    Compute Word Error Rate (WER) using dynamic programming Levenshtein distance on words.
    WER = (Substitutions + Deletions + Insertions) / Total Reference Words
    """
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)

    ref_words = ref_norm.split() if ref_norm else []
    hyp_words = hyp_norm.split() if hyp_norm else []

    r_len = len(ref_words)
    h_len = len(hyp_words)

    if r_len == 0:
        if h_len == 0:
            return {
                "wer": 0.0,
                "substitutions": 0,
                "deletions": 0,
                "insertions": 0,
                "correct": 0,
                "ref_word_count": 0,
                "hyp_word_count": 0,
            }
        return {
            "wer": 1.0,
            "substitutions": 0,
            "deletions": 0,
            "insertions": h_len,
            "correct": 0,
            "ref_word_count": 0,
            "hyp_word_count": h_len,
        }

    # DP Matrix: dp[i][j] = (cost, subs, dels, ins)
    dp = [[0] * (h_len + 1) for _ in range(r_len + 1)]
    for i in range(r_len + 1):
        dp[i][0] = i
    for j in range(h_len + 1):
        dp[0][j] = j

    for i in range(1, r_len + 1):
        for j in range(1, h_len + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                substitution = dp[i - 1][j - 1] + 1
                deletion = dp[i - 1][j] + 1
                insertion = dp[i][j - 1] + 1
                dp[i][j] = min(substitution, deletion, insertion)

    # Backtrack to count S, D, I, C
    i, j = r_len, h_len
    subs, dels, ins, correct = 0, 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_words[i - 1] == hyp_words[j - 1]:
            correct += 1
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            subs += 1
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            dels += 1
            i -= 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            ins += 1
            j -= 1
        else:
            # Fallback tie-break
            if i > 0 and j > 0:
                subs += 1
                i -= 1
                j -= 1
            elif i > 0:
                dels += 1
                i -= 1
            else:
                ins += 1
                j -= 1

    total_errors = subs + dels + ins
    wer_score = total_errors / r_len

    return {
        "wer": round(wer_score, 6),
        "substitutions": subs,
        "deletions": dels,
        "insertions": ins,
        "correct": correct,
        "ref_word_count": r_len,
        "hyp_word_count": h_len,
    }


def calculate_cer(reference: str, hypothesis: str, ignore_whitespace: bool = True) -> Dict[str, Any]:
    """
    Compute Character Error Rate (CER) on character sequences.
    Standard for CJK and multilingual Indic evaluation.
    """
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)

    if ignore_whitespace:
        ref_chars = [c for c in ref_norm if not c.isspace()]
        hyp_chars = [c for c in hyp_norm if not c.isspace()]
    else:
        ref_chars = list(ref_norm)
        hyp_chars = list(hyp_norm)

    r_len = len(ref_chars)
    h_len = len(hyp_chars)

    if r_len == 0:
        if h_len == 0:
            return {
                "cer": 0.0,
                "substitutions": 0,
                "deletions": 0,
                "insertions": 0,
                "correct": 0,
                "ref_char_count": 0,
                "hyp_char_count": 0,
            }
        return {
            "cer": 1.0,
            "substitutions": 0,
            "deletions": 0,
            "insertions": h_len,
            "correct": 0,
            "ref_char_count": 0,
            "hyp_char_count": h_len,
        }

    dp = [[0] * (h_len + 1) for _ in range(r_len + 1)]
    for i in range(r_len + 1):
        dp[i][0] = i
    for j in range(h_len + 1):
        dp[0][j] = j

    for i in range(1, r_len + 1):
        for j in range(1, h_len + 1):
            if ref_chars[i - 1] == hyp_chars[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(dp[i - 1][j - 1] + 1, dp[i - 1][j] + 1, dp[i][j - 1] + 1)

    i, j = r_len, h_len
    subs, dels, ins, correct = 0, 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_chars[i - 1] == hyp_chars[j - 1]:
            correct += 1
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            subs += 1
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            dels += 1
            i -= 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            ins += 1
            j -= 1
        else:
            if i > 0 and j > 0:
                subs += 1
                i -= 1
                j -= 1
            elif i > 0:
                dels += 1
                i -= 1
            else:
                ins += 1
                j -= 1

    total_errors = subs + dels + ins
    cer_score = total_errors / r_len

    return {
        "cer": round(cer_score, 6),
        "substitutions": subs,
        "deletions": dels,
        "insertions": ins,
        "correct": correct,
        "ref_char_count": r_len,
        "hyp_char_count": h_len,
    }


def _hungarian_max_weight_matching(cost_matrix: List[List[float]]) -> List[Tuple[int, int]]:
    """
    Pure Python Maximum Weight Bipartite Matching algorithm for speaker alignment.
    Given an MxN overlap matrix between reference speakers and hypothesis speakers,
    finds the 1-to-1 assignment that maximizes total overlap duration.
    """
    if not cost_matrix or not cost_matrix[0]:
        return []

    n_rows = len(cost_matrix)
    n_cols = len(cost_matrix[0])
    
    # Greedy with augmenting path for integer/float bipartite maximum matching
    # Since speaker counts in meeting segments are typically <= 10, exact branch & bound is fast and optimal
    best_matching: List[Tuple[int, int]] = []
    max_weight = -1.0

    def search_matching(row: int, current_matching: List[Tuple[int, int]], used_cols: Set[int], current_weight: float):
        nonlocal max_weight, best_matching
        if row == n_rows:
            if current_weight > max_weight:
                max_weight = current_weight
                best_matching = list(current_matching)
            return

        # Option 1: Try matching `row` to an available column
        matched_any = False
        sorted_cols = sorted(range(n_cols), key=lambda c: cost_matrix[row][c], reverse=True)
        for col in sorted_cols:
            if col not in used_cols and cost_matrix[row][col] > 0.0:
                matched_any = True
                used_cols.add(col)
                current_matching.append((row, col))
                search_matching(row + 1, current_matching, used_cols, current_weight + cost_matrix[row][col])
                current_matching.pop()
                used_cols.remove(col)

        # Option 2: Leave `row` unmatched
        search_matching(row + 1, current_matching, used_cols, current_weight)

    search_matching(0, [], set(), 0.0)
    return best_matching


def calculate_der(
    reference_turns: List[Dict[str, Any]],
    hypothesis_turns: List[Dict[str, Any]],
    collar_seconds: float = 0.25,
    step_ms: float = 10.0,
) -> Dict[str, Any]:
    """
    Calculate Diarization Error Rate (DER) according to NIST / pyannote standards.
    DER = (Missed Speech + False Alarm + Speaker Confusion) / Total Reference Speech Time.
    Includes configurable evaluation collar (default: 250ms) around reference turn boundaries.
    """
    if not reference_turns:
        if not hypothesis_turns:
            return {
                "der": 0.0,
                "missed_speech_rate": 0.0,
                "false_alarm_rate": 0.0,
                "speaker_confusion_rate": 0.0,
                "missed_speech_seconds": 0.0,
                "false_alarm_seconds": 0.0,
                "speaker_confusion_seconds": 0.0,
                "total_reference_speech_seconds": 0.0,
            }
        hyp_dur = sum(t.get("end_time", 0.0) - t.get("start_time", 0.0) for t in hypothesis_turns)
        return {
            "der": 1.0,
            "missed_speech_rate": 0.0,
            "false_alarm_rate": 1.0,
            "speaker_confusion_rate": 0.0,
            "missed_speech_seconds": 0.0,
            "false_alarm_seconds": hyp_dur,
            "speaker_confusion_seconds": 0.0,
            "total_reference_speech_seconds": 0.0,
        }

    # Identify all reference & hypothesis unique speakers
    ref_speakers = sorted(list(set(t["speaker"] for t in reference_turns)))
    hyp_speakers = sorted(list(set(t["speaker"] for t in hypothesis_turns))) if hypothesis_turns else []

    ref_spk_to_idx = {spk: i for i, spk in enumerate(ref_speakers)}
    hyp_spk_to_idx = {spk: i for i, spk in enumerate(hyp_speakers)}

    # Determine timeline extent
    min_time = min(t["start_time"] for t in reference_turns)
    max_time = max(t["end_time"] for t in reference_turns)
    if hypothesis_turns:
        min_time = min(min_time, min(t["start_time"] for t in hypothesis_turns))
        max_time = max(max_time, max(t["end_time"] for t in hypothesis_turns))

    # Build collar mask intervals around reference boundaries
    collar_intervals: List[Tuple[float, float]] = []
    if collar_seconds > 0.0:
        for t in reference_turns:
            collar_intervals.append((max(0.0, t["start_time"] - collar_seconds), t["start_time"] + collar_seconds))
            collar_intervals.append((max(0.0, t["end_time"] - collar_seconds), t["end_time"] + collar_seconds))

    def in_collar(time_s: float) -> bool:
        for c_start, c_end in collar_intervals:
            if c_start <= time_s <= c_end:
                return True
        return False

    # Discretize timeline in 10ms frames
    step_s = step_ms / 1000.0
    n_steps = int(math.ceil((max_time - min_time) / step_s)) + 1

    # Overlap matrix: co_occurrence[ref_idx][hyp_idx] = overlapping duration
    co_occurrence = [[0.0] * len(hyp_speakers) for _ in range(len(ref_speakers))]

    # Track active speaker sets per frame
    # Frame i corresponds to time_s = min_time + i * step_s
    frame_ref: List[Set[int]] = [set() for _ in range(n_steps)]
    frame_hyp: List[Set[int]] = [set() for _ in range(n_steps)]
    frame_in_collar: List[bool] = [False] * n_steps

    for i in range(n_steps):
        t_cur = min_time + i * step_s
        frame_in_collar[i] = in_collar(t_cur)

    for t in reference_turns:
        s_idx = ref_spk_to_idx[t["speaker"]]
        start_i = max(0, int((t["start_time"] - min_time) / step_s))
        end_i = min(n_steps - 1, int((t["end_time"] - min_time) / step_s))
        for i in range(start_i, end_i + 1):
            frame_ref[i].add(s_idx)

    for t in hypothesis_turns:
        if t["speaker"] in hyp_spk_to_idx:
            s_idx = hyp_spk_to_idx[t["speaker"]]
            start_i = max(0, int((t["start_time"] - min_time) / step_s))
            end_i = min(n_steps - 1, int((t["end_time"] - min_time) / step_s))
            for i in range(start_i, end_i + 1):
                frame_hyp[i].add(s_idx)

    # Accumulate co-occurrence (only for non-collar frames)
    for i in range(n_steps):
        if frame_in_collar[i]:
            continue
        for r_s in frame_ref[i]:
            for h_s in frame_hyp[i]:
                co_occurrence[r_s][h_s] += step_s

    # Compute optimal 1-to-1 speaker alignment mapping
    matching = _hungarian_max_weight_matching(co_occurrence)
    ref_to_hyp_map: Dict[int, int] = {r: h for r, h in matching}
    hyp_to_ref_map: Dict[int, int] = {h: r for r, h in matching}

    # Evaluate errors across all frames
    total_ref_duration = 0.0
    missed_speech_duration = 0.0
    false_alarm_duration = 0.0
    speaker_confusion_duration = 0.0

    for i in range(n_steps):
        if frame_in_collar[i]:
            continue

        r_set = frame_ref[i]
        h_set = frame_hyp[i]
        r_count = len(r_set)
        h_count = len(h_set)

        total_ref_duration += r_count * step_s

        if r_count > h_count:
            # More reference speakers than hypothesis -> Missed Speech
            missed_speech_duration += (r_count - h_count) * step_s
        elif h_count > r_count:
            # More hypothesis speakers than reference -> False Alarm
            false_alarm_duration += (h_count - r_count) * step_s

        # For the overlapping number of speakers min(r_count, h_count), check if mapped correctly
        overlap_count = min(r_count, h_count)
        if overlap_count > 0:
            # Count how many mapped pairs match
            correct_pairs = sum(1 for r_s in r_set if ref_to_hyp_map.get(r_s) in h_set)
            confused_pairs = overlap_count - correct_pairs
            speaker_confusion_duration += max(0, confused_pairs) * step_s

    if total_ref_duration == 0.0:
        der_score = 0.0 if false_alarm_duration == 0.0 else 1.0
        missed_rate = 0.0
        fa_rate = 0.0 if false_alarm_duration == 0.0 else 1.0
        confusion_rate = 0.0
    else:
        missed_rate = missed_speech_duration / total_ref_duration
        fa_rate = false_alarm_duration / total_ref_duration
        confusion_rate = speaker_confusion_duration / total_ref_duration
        der_score = (missed_speech_duration + false_alarm_duration + speaker_confusion_duration) / total_ref_duration

    return {
        "der": round(der_score, 6),
        "missed_speech_rate": round(missed_rate, 6),
        "false_alarm_rate": round(fa_rate, 6),
        "speaker_confusion_rate": round(confusion_rate, 6),
        "missed_speech_seconds": round(missed_speech_duration, 4),
        "false_alarm_seconds": round(false_alarm_duration, 4),
        "speaker_confusion_seconds": round(speaker_confusion_duration, 4),
        "total_reference_speech_seconds": round(total_ref_duration, 4),
        "mapped_speaker_pairs": {
            ref_speakers[r]: hyp_speakers[h] for r, h in matching
        },
    }


def calculate_timestamp_boundary_error(
    reference_segments: List[Dict[str, Any]],
    hypothesis_segments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Measure alignment error between ground-truth and predicted segment timestamps.
    Returns mean, median, max, and std deviation boundary errors in milliseconds.
    """
    if not reference_segments or not hypothesis_segments:
        return {
            "mean_boundary_error_ms": 0.0,
            "median_boundary_error_ms": 0.0,
            "max_boundary_error_ms": 0.0,
            "std_boundary_error_ms": 0.0,
            "matched_segments_count": 0,
        }

    errors_ms: List[float] = []
    # Match hypothesis segments to nearest overlapping/adjacent reference segments
    for h_seg in hypothesis_segments:
        h_start = float(h_seg.get("start_time", 0.0))
        h_end = float(h_seg.get("end_time", 0.0))

        # Find best matching reference segment
        best_delta = float("inf")
        for r_seg in reference_segments:
            r_start = float(r_seg.get("start_time", 0.0))
            r_end = float(r_seg.get("end_time", 0.0))
            delta = abs(h_start - r_start) + abs(h_end - r_end)
            if delta < best_delta:
                best_delta = delta

        if best_delta < float("inf"):
            errors_ms.append(best_delta * 1000.0 / 2.0)  # average start/end error in ms

    if not errors_ms:
        return {
            "mean_boundary_error_ms": 0.0,
            "median_boundary_error_ms": 0.0,
            "max_boundary_error_ms": 0.0,
            "std_boundary_error_ms": 0.0,
            "matched_segments_count": 0,
        }

    mean_err = sum(errors_ms) / len(errors_ms)
    sorted_err = sorted(errors_ms)
    mid = len(sorted_err) // 2
    median_err = (sorted_err[mid] if len(sorted_err) % 2 != 0 else (sorted_err[mid - 1] + sorted_err[mid]) / 2.0)
    max_err = max(errors_ms)
    variance = sum((x - mean_err) ** 2 for x in errors_ms) / len(errors_ms)
    std_err = math.sqrt(variance)

    return {
        "mean_boundary_error_ms": round(mean_err, 2),
        "median_boundary_error_ms": round(median_err, 2),
        "max_boundary_error_ms": round(max_err, 2),
        "std_boundary_error_ms": round(std_err, 2),
        "matched_segments_count": len(errors_ms),
    }


def calculate_rtf(processing_time_seconds: float, audio_duration_seconds: float) -> float:
    """Compute Real-Time Factor: processing time / audio duration."""
    if audio_duration_seconds <= 0.0:
        return 0.0
    return round(processing_time_seconds / audio_duration_seconds, 4)
