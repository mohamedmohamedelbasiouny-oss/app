"""المراحل 5 و 6 و 7: القرار، المقام، والتحويلات بين المقامات.

الطريقة:
1. توزيع النوتات على 24 درجة (pitch histogram) لكل مقطع زمني.
2. احتمال القرار لكل درجة: النوتات اللي الجمل بتقفل عليها + المدة + المنطقة الواطية.
3. لكل مقام ولكل قرار محتمل: مقارنة الأجناس (الجنس الأساسي أهم) بالتوزيع،
   وعقاب على النوتات اللي برة السلم.
4. تقسيم الأغنية لمقاطع وتحديد المقام في كل مقطع، مع Viterbi عشان
   ما يقلبش كل شوية من غير سبب (التحويلات الحقيقية بس هي اللي تظهر).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .maqam_db import AJNAS, MAQAMAT, Maqam, maqam_color
from .notes import tonic_label, pc_label
from .transcribe import NoteEvent, pitch_class_histogram


@dataclass
class MaqamCandidate:
    maqam: Maqam
    tonic: int              # 0..23
    score: float
    fit: float              # نسبة النوتات اللي جوه السلم
    probability: float = 0.0

    @property
    def name(self) -> str:
        return self.maqam.name_ar

    @property
    def tonic_text(self) -> str:
        return tonic_label(self.tonic)

    @property
    def color(self) -> str:
        return maqam_color(self.maqam.key)

    @property
    def display_name(self) -> str:
        """اسم المقام، ولو متصوّر على قرار غير التقليدي بنقول عليه."""
        from .maqam_db import TRANSPOSED_NAMES
        from .notes import tonic_label as _tl

        special = TRANSPOSED_NAMES.get((self.maqam.key, self.tonic))
        if special:
            return special
        if self.tonic == self.maqam.default_tonic:
            return self.maqam.name_ar
        return f"{self.maqam.name_ar} على {_tl(self.tonic).split(' = ')[0]}"

    def title(self) -> str:
        return f"{self.display_name} — القرار: {tonic_label(self.tonic)}"

    def ajnas_desc(self) -> list[str]:
        out = []
        for jk, off in self.maqam.ajnas:
            j = AJNAS[jk]
            root = (self.tonic + off) % 24
            out.append(f"جنس {j.name_ar} {j.kind} على {pc_label(root)}")
        return out

    def scale_pcs(self) -> list[int]:
        return [(self.tonic + s) % 24 for s in self.maqam.scale]


@dataclass
class Section:
    start: float
    end: float
    candidate: MaqamCandidate
    alternatives: list[MaqamCandidate] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class MaqamResult:
    global_best: MaqamCandidate
    ranking: list[MaqamCandidate]
    sections: list[Section]
    histogram: np.ndarray
    tonic_probs: np.ndarray


# ---------------------------------------------------------------- القرار

def tonic_evidence(notes: list[NoteEvent], phrase_gap: float = 0.25) -> np.ndarray:
    """احتمال إن كل درجة (0..23) تكون القرار."""
    end_w = np.zeros(24)
    dur_w = np.zeros(24)
    low_w = np.zeros(24)
    clear = [n for n in notes if n.confidence >= 0.35]
    if not clear:
        return np.full(24, 1 / 24)
    lows = np.array([n.cents for n in clear])
    lo_thr = np.percentile(lows, 35)
    for i, n in enumerate(clear):
        pc = n.pc24
        d = min(n.duration, 1.5) * n.confidence
        dur_w[pc] += d
        nxt = clear[i + 1] if i + 1 < len(clear) else None
        is_end = nxt is None or (nxt.start - n.end) >= phrase_gap
        if is_end:
            end_w[pc] += max(d, 0.15) * (2.5 if nxt is None else 1.0)
        if n.cents <= lo_thr:
            low_w[pc] += d

    def norm(v):
        s = v.sum()
        return v / s if s > 0 else np.full(24, 1 / 24)

    t = 0.55 * norm(end_w) + 0.30 * norm(dur_w) + 0.15 * norm(low_w)
    return norm(t)


# ---------------------------------------------------------------- مقارنة المقامات

def _score(m: Maqam, tonic: int, h: np.ndarray, tonic_rel: np.ndarray) -> tuple[float, float]:
    scale = [(tonic + s) % 24 for s in m.scale]
    alts = [(tonic + a) % 24 for a in m.alternates]
    in_scale = h[scale].sum()
    alt_mass = h[list(set(alts) - set(scale))].sum() if alts else 0.0
    out = max(0.0, 1.0 - in_scale - alt_mass)

    lower = sorted({(tonic + s) % 24 for s in m.lower_notes()})
    upper = sorted({(tonic + s) % 24 for s in m.upper_notes()} - set(lower))
    lower_present = np.mean([min(1.0, h[p] / 0.025) for p in lower])
    upper_present = np.mean([min(1.0, h[p] / 0.02) for p in upper]) if upper else 1.0

    # الغماز (أساس الجنس الفرعي) عادة نوتة مهمة
    gh = (tonic + m.ghammaz_pos()) % 24
    ghammaz_term = min(1.0, h[gh] / 0.08)

    score = (in_scale + 0.5 * alt_mass
             - 2.2 * out
             + 0.30 * lower_present
             + 0.08 * upper_present
             + 0.05 * ghammaz_term
             + 0.45 * tonic_rel[tonic]
             + m.prior)
    return float(score), float(in_scale + alt_mass)


def rank_maqamat(h: np.ndarray, tonic_probs: np.ndarray,
                 tonic_candidates: int = 8) -> list[MaqamCandidate]:
    tonic_rel = tonic_probs / (tonic_probs.max() + 1e-12)
    # بنجرب القرارات الأكتر احتمالاً بس (أسرع وأدق)
    tonics = set(np.argsort(tonic_probs)[::-1][:tonic_candidates].tolist())
    tonics |= set(np.argsort(h)[::-1][:6].tolist())
    cands = []
    for m in MAQAMAT:
        for t in tonics:
            if h[t] < 0.01:
                continue
            s, fit = _score(m, t, h, tonic_rel)
            cands.append(MaqamCandidate(m, int(t), s, fit))
    if not cands:
        m = MAQAMAT[0]
        return [MaqamCandidate(m, m.default_tonic, 0.0, 0.0, 1.0)]
    cands.sort(key=lambda c: c.score, reverse=True)
    scores = np.array([c.score for c in cands])
    p = np.exp((scores - scores.max()) / 0.05)
    p /= p.sum()
    for c, pi in zip(cands, p):
        c.probability = float(pi)
    return cands


# ---------------------------------------------------------------- المقاطع والتحويلات

def _window_hist(times, cents, conf, t0, t1):
    m = (times >= t0) & (times < t1)
    return pitch_class_histogram(cents[m], conf[m]), int(np.isfinite(cents[m]).sum())


def detect(times: np.ndarray, cents: np.ndarray, conf: np.ndarray,
           notes: list[NoteEvent], duration: float,
           window: float = 16.0, hop: float = 4.0,
           switch_penalty: float = 0.35) -> MaqamResult:
    h_global = pitch_class_histogram(cents, conf)
    t_global = tonic_evidence(notes)
    ranking = rank_maqamat(h_global, t_global)
    best = ranking[0]

    # نوافذ زمنية متداخلة
    starts = np.arange(0.0, max(duration - window * 0.5, 0.0) + 1e-9, hop)
    if len(starts) == 0:
        starts = np.array([0.0])
    win_data = []
    for s in starts:
        e = min(s + window, duration)
        h, n_voiced = _window_hist(times, cents, conf, s, e)
        win_notes = [n for n in notes if s <= n.start < e]
        win_data.append((s, e, h, n_voiced, win_notes))

    # الحالات المرشحة = أحسن 4 في كل نافذة + أحسن 6 على مستوى الأغنية
    state_keys: dict[tuple[str, int], MaqamCandidate] = {}
    for c in ranking[:6]:
        state_keys[(c.maqam.key, c.tonic)] = c
    win_rank = []
    min_frames = 0.8 / max(float(times[1] - times[0]), 1e-3) if len(times) > 1 else 50
    for (s, e, h, nv, wn) in win_data:
        if nv < min_frames:
            win_rank.append(None)
            continue
        # بنخلط شوية من التوزيع العام عشان النوافذ القصيرة ما تتلخبطش
        hw = 0.8 * h + 0.2 * h_global
        tw = 0.75 * tonic_evidence(wn) + 0.25 * t_global
        r = rank_maqamat(hw, tw)
        win_rank.append(r)
        for c in r[:4]:
            state_keys.setdefault((c.maqam.key, c.tonic), c)

    states = list(state_keys.keys())
    S, W = len(states), len(win_data)
    if W == 0 or S == 0:
        return MaqamResult(best, ranking, [Section(0.0, duration, best, ranking[1:4])],
                           h_global, t_global)

    from .maqam_db import MAQAM_BY_KEY

    emis = np.zeros((W, S))
    for w, (s, e, h, nv, wn) in enumerate(win_data):
        if win_rank[w] is None:
            continue  # نافذة صامتة: كل الحالات متساوية
        hw = 0.8 * h + 0.2 * h_global
        tw = 0.75 * tonic_evidence(wn) + 0.25 * t_global
        trel = tw / (tw.max() + 1e-12)
        for k, (mk, t) in enumerate(states):
            emis[w, k], _ = _score(MAQAM_BY_KEY[mk], t, hw, trel)

    # Viterbi: البقاء في نفس المقام مجاني، والتحويل عليه غرامة
    dp = np.zeros((W, S))
    bp = np.zeros((W, S), dtype=int)
    dp[0] = emis[0]
    for w in range(1, W):
        stay = dp[w - 1]
        best_prev = int(np.argmax(dp[w - 1]))
        switch = dp[w - 1, best_prev] - switch_penalty
        for k in range(S):
            if stay[k] >= switch:
                dp[w, k] = stay[k] + emis[w, k]
                bp[w, k] = k
            else:
                dp[w, k] = switch + emis[w, k]
                bp[w, k] = best_prev
    path = [int(np.argmax(dp[-1]))]
    for w in range(W - 1, 0, -1):
        path.append(int(bp[w, path[-1]]))
    path.reverse()

    # تحويل المسار لمقاطع (حدود المقطع في نص المسافة بين النوافذ)
    sections: list[Section] = []
    ctx = (times, cents, conf, notes, h_global, t_global)
    centers = [(s + e) / 2 for (s, e, *_r) in win_data]
    cur = path[0]
    seg_start = 0.0
    for w in range(1, W):
        if path[w] != cur:
            boundary = (centers[w - 1] + centers[w]) / 2
            sections.append(_make_section(seg_start, boundary, states[cur], ctx))
            seg_start = boundary
            cur = path[w]
    sections.append(_make_section(seg_start, duration, states[cur], ctx))

    # لو المقطع قصير جدًا (أقل من 8 ثواني) ندمجه مع اللي قبله
    merged: list[Section] = []
    for sec in sections:
        if merged and sec.duration < 8.0:
            merged[-1].end = sec.end
            continue
        if merged and (merged[-1].candidate.maqam.key, merged[-1].candidate.tonic) == \
                (sec.candidate.maqam.key, sec.candidate.tonic):
            merged[-1].end = sec.end
            continue
        merged.append(sec)
    if len(merged) > 1 and merged[0].duration < 8.0:
        merged[1].start = merged[0].start
        merged.pop(0)
    return MaqamResult(best, ranking, merged, h_global, t_global)


def _make_section(t0, t1, state, ctx) -> Section:
    from .maqam_db import MAQAM_BY_KEY

    times, cents, conf, notes, h_global, t_global = ctx
    # نعيد التقييم على المقطع كله عشان الاحتمالات والبدائل
    h, _ = _window_hist(times, cents, conf, t0, t1)
    notes_in = [n for n in notes if t0 <= n.start < t1]
    tw = tonic_evidence(notes_in) if notes_in else t_global
    ranking = rank_maqamat(0.85 * h + 0.15 * h_global, 0.75 * tw + 0.25 * t_global)
    mk, t = state
    chosen = next((c for c in ranking if c.maqam.key == mk and c.tonic == t), None)
    if chosen is None:
        chosen = MaqamCandidate(MAQAM_BY_KEY[mk], t, 0.0, 0.0, 0.0)
    alts = [c for c in ranking if c is not chosen][:3]
    return Section(float(t0), float(t1), chosen, alts)
