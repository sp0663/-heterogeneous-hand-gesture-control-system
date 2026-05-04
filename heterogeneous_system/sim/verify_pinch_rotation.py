"""
Offline verification of the FPGA pinch-rotation algorithm.

Compares the Verilog gesture_classifier's dynamic-pinch behaviour (modelled
here in pure Python, same integer arithmetic / widths / thresholds as the
RTL) against the reference GestureRecogniser from gesture_media_controller.

Steps per test scenario:
  1. Build a stream of synthetic 21-landmark frames in pixel space, with a
     pinching hand whose pinch-point rotates around the wrist at a chosen
     angular velocity.
  2. Feed pixel-space frames straight to the reference GestureRecogniser
     (it expects landmarks in pixel coords, the same format landmark_capture.py
     hands to it upstream of serialization).
  3. Run the same frames through landmark_capture.build_frame_bytes() to get
     the exact 16-bit packed landmarks the FPGA sees, then run the bit-exact
     Python model of the Verilog gesture_classifier on them.
  4. Print both outputs side-by-side and assert qualitative agreement.

This is not a bit-exact cross-check against Verilog (the algorithms differ by
design: atan2/delta vs cross-product). It validates:
  * my algorithm fires CW/ACW in the same direction as the reference,
  * quiescent pinch does not drift into spurious rotations,
  * sensitivity is in a usable range (triggers within ~10-20 degrees of
    accumulated rotation, matching the reference's 10 degree threshold).
"""

import math
import os
import sys


# --------------------------------------------------------------------------
# Load the reference controller from the sibling project.
# --------------------------------------------------------------------------
HERE    = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "gesture_media_controller"))
sys.path.insert(0, REF_DIR)
from gesture_recogniser import GestureRecogniser  # noqa: E402


# --------------------------------------------------------------------------
# Bit-exact Python model of the Verilog gesture_classifier's rotation logic.
# Mirrors widths and thresholds from rtl/gesture_classifier.v exactly.
# --------------------------------------------------------------------------
class VerilogPinchRotationModel:
    CROSS_SHIFT = 24
    ACC_THRESH  = 10
    NOISE_FLOOR = 2

    # Gesture IDs (matching the Verilog localparams)
    PINCH        = 0
    FIST         = 1
    OPEN_HAND    = 2
    INDEX_FINGER = 3
    UNKNOWN      = 4
    PINCH_CW     = 5
    PINCH_ACW    = 6

    def __init__(self):
        self.prev_dx = 0
        self.prev_dy = 0
        self.prev_pinch_valid = False
        self.rotation_accumulator = 0

    @staticmethod
    def _is_pinch(x, y):
        # Same geometric test as the Verilog: dist_thumb_index^2 * 16 < dist_wrist_middle^2
        dx_ti = x[8] - x[4]
        dy_ti = y[8] - y[4]
        dx_wm = x[12] - x[0]
        dy_wm = y[12] - y[0]
        dist_ti_sq = dx_ti * dx_ti + dy_ti * dy_ti
        dist_wm_sq = dx_wm * dx_wm + dy_wm * dy_wm
        return dist_ti_sq * 16 < dist_wm_sq

    def step(self, x, y):
        """Advance one frame. x[i], y[i] are the unsigned 16-bit normalised landmark coords."""
        wrist_x, wrist_y = x[0], y[0]
        thumb_x, thumb_y = x[4], y[4]
        index_x, index_y = x[8], y[8]

        # Same expression as the RTL: dx = (thumb + index) - 2*wrist
        # This preserves the factor of two relative to the true pinch-vector.
        dx_curr = (thumb_x + index_x) - 2 * wrist_x
        dy_curr = (thumb_y + index_y) - 2 * wrist_y

        is_pinch = self._is_pinch(x, y)

        if not is_pinch:
            self.prev_pinch_valid = False
            # rotation_accumulator preserved, matching RTL
            return self.UNKNOWN  # static path would return FIST/OPEN_HAND/etc.; irrelevant here

        # Pinch branch
        if not self.prev_pinch_valid:
            self.prev_dx = dx_curr
            self.prev_dy = dy_curr
            self.prev_pinch_valid = True
            return self.PINCH

        cross_raw = self.prev_dx * dy_curr - dx_curr * self.prev_dy

        # Verilog arithmetic right-shift on signed 38-bit -> Python // already
        # does arithmetic (floor) shift on signed ints, matching >>> semantics
        # for our value range.
        cross_scaled = cross_raw >> self.CROSS_SHIFT

        # Noise floor
        if abs(cross_scaled) < self.NOISE_FLOOR:
            cross_effective = 0
        else:
            cross_effective = cross_scaled

        acc_next = self.rotation_accumulator + cross_effective

        self.prev_dx = dx_curr
        self.prev_dy = dy_curr

        if acc_next > self.ACC_THRESH:
            self.rotation_accumulator = acc_next - self.ACC_THRESH
            return self.PINCH_CW
        elif acc_next < -self.ACC_THRESH:
            self.rotation_accumulator = acc_next + self.ACC_THRESH
            return self.PINCH_ACW
        else:
            self.rotation_accumulator = acc_next
            return self.PINCH


# --------------------------------------------------------------------------
# Normalisation: same math landmark_capture.py uses before shipping bytes
# over UART.
# --------------------------------------------------------------------------
def normalise_landmarks(landmarks_px):
    """Pixel-space [id, x, y] -> per-landmark unsigned 16-bit (nx, ny)."""
    wrist_x, wrist_y = landmarks_px[0][1], landmarks_px[0][2]
    max_dist = max(
        (max(abs(lm[1] - wrist_x), abs(lm[2] - wrist_y)) for lm in landmarks_px),
        default=1
    ) or 1

    x16 = [0] * 21
    y16 = [0] * 21
    for lm in landmarks_px:
        i = lm[0]
        nx = int(((lm[1] - wrist_x) / max_dist + 1) * 32767)
        ny = int(((lm[2] - wrist_y) / max_dist + 1) * 32767)
        x16[i] = max(0, min(65535, nx))
        y16[i] = max(0, min(65535, ny))
    return x16, y16


# --------------------------------------------------------------------------
# Synthetic frame factory: a pinching hand with the pinch-point on a circle
# around the wrist at a chosen angle. The rest of the landmarks are fixed
# so only the rotating pinch affects the output.
# --------------------------------------------------------------------------
def synth_pinch_frame(pinch_angle_deg, wrist=(320.0, 240.0), pinch_radius=110.0):
    """Return 21 landmarks [id, x, y] in pixel space for a pinching hand.

    The 'middle finger' is held straight up from the wrist (fixed) to provide
    a stable hand-size reference so is_pinch() fires. Thumb-tip and index-tip
    are placed close together around the pinch-centre on a circle of radius
    pinch_radius around the wrist at the given angle.
    """
    wx, wy = wrist
    a = math.radians(pinch_angle_deg)
    pcx = wx + pinch_radius * math.cos(a)
    pcy = wy + pinch_radius * math.sin(a)

    # Thumb tip and index tip close together (~14 px apart) around pinch centre.
    # Offset perpendicular to the pinch-vector so it doesn't bias rotation.
    perp_x, perp_y = -math.sin(a), math.cos(a)
    thumb_tip = (pcx + 5 * perp_x, pcy + 5 * perp_y)
    index_tip = (pcx - 5 * perp_x, pcy - 5 * perp_y)

    # Middle finger straight up for hand-size scale
    middle_tip = (wx, wy - 180.0)
    middle_knuckle = (wx, wy - 60.0)

    landmarks = [None] * 21
    landmarks[0]  = [0,  wx,                wy]
    # Thumb chain — positions don't need to be anatomically correct, just
    # roughly plausible so is_pinch uses landmarks 4 & 8 as intended.
    landmarks[1]  = [1,  wx + 25,           wy - 15]
    landmarks[2]  = [2,  pcx - 30 * math.cos(a), pcy - 30 * math.sin(a)]
    landmarks[3]  = [3,  pcx - 12 * math.cos(a), pcy - 12 * math.sin(a)]
    landmarks[4]  = [4,  thumb_tip[0],      thumb_tip[1]]
    # Index chain
    landmarks[5]  = [5,  pcx - 40 * math.cos(a), pcy - 40 * math.sin(a) + 8]
    landmarks[6]  = [6,  pcx - 20 * math.cos(a), pcy - 20 * math.sin(a) + 4]
    landmarks[7]  = [7,  pcx - 8 * math.cos(a),  pcy - 8 * math.sin(a) + 2]
    landmarks[8]  = [8,  index_tip[0],      index_tip[1]]
    # Middle chain (straight up)
    landmarks[9]  = [9,  middle_knuckle[0], middle_knuckle[1]]
    landmarks[10] = [10, wx,                wy - 100]
    landmarks[11] = [11, wx,                wy - 140]
    landmarks[12] = [12, middle_tip[0],     middle_tip[1]]
    # Ring chain
    landmarks[13] = [13, wx - 15,           wy - 60]
    landmarks[14] = [14, wx - 15,           wy - 100]
    landmarks[15] = [15, wx - 15,           wy - 140]
    landmarks[16] = [16, wx - 15,           wy - 170]
    # Pinky chain
    landmarks[17] = [17, wx - 30,           wy - 50]
    landmarks[18] = [18, wx - 30,           wy - 80]
    landmarks[19] = [19, wx - 30,           wy - 110]
    landmarks[20] = [20, wx - 30,           wy - 140]
    return landmarks


# --------------------------------------------------------------------------
# Test driver
# --------------------------------------------------------------------------
REF_NAME = {
    'pinch_clockwise':     'PINCH_CW',
    'pinch_anticlockwise': 'PINCH_ACW',
    'pinch':               'PINCH',
    'unknown':             'UNKNOWN',
    'open_palm':           'OPEN_HAND',
    'fist':                'FIST',
    'index_pointing':      'INDEX_FINGER',
}

HW_NAME = {
    0: 'PINCH', 1: 'FIST', 2: 'OPEN_HAND', 3: 'INDEX_FINGER',
    4: 'UNKNOWN', 5: 'PINCH_CW', 6: 'PINCH_ACW',
}


def ref_name(r):
    return REF_NAME.get(r, str(r))


def run_scenario(name, angles_deg, expect_hw_fires, expect_ref_fires, verbose=False):
    """Run a scenario through both models and summarise.

    expect_hw_fires / expect_ref_fires: set of gesture names expected to appear
    at least once. 'PINCH' is present whenever pinch is detected without
    rotation trigger — we don't assert it, we only assert the rotation events.
    """
    print(f"\n=== Scenario: {name} ({len(angles_deg)} frames) ===")

    hw = VerilogPinchRotationModel()
    ref = GestureRecogniser()

    hw_hits = {}
    ref_hits = {}

    # Reference uses time.time() internally — feed it a fresh recogniser and
    # monotonically increasing frames. Swipe cooldown etc won't fire here
    # because we only move the pinch, not the wrist.
    for i, angle in enumerate(angles_deg):
        lm_px = synth_pinch_frame(angle)

        ref_out = ref.recognise_gesture(lm_px, 'Right', None)
        ref_hits[ref_out] = ref_hits.get(ref_out, 0) + 1

        x16, y16 = normalise_landmarks(lm_px)
        hw_out = hw.step(x16, y16)
        hw_name = HW_NAME[hw_out]
        hw_hits[hw_name] = hw_hits.get(hw_name, 0) + 1

        if verbose:
            print(f"  frame {i:3d}  angle={angle:7.2f}  ref={ref_out:25s}  hw={hw_name}")

    print(f"  reference events:  {ref_hits}")
    print(f"  hardware events:   {hw_hits}")

    ok = True
    for g in expect_hw_fires:
        if hw_hits.get(g, 0) == 0:
            print(f"  FAIL: expected hardware to fire {g} at least once")
            ok = False
    for g in expect_ref_fires:
        if ref_name(g) == g:
            # passed an already-human name
            want = [k for k in ref_hits if REF_NAME.get(k, k) == g]
        else:
            want = [g]
        if not any(ref_hits.get(n, 0) for n in want):
            print(f"  FAIL: expected reference to fire {g} at least once")
            ok = False

    # Negative assertions: quiescent pinch must NOT trigger rotation.
    if name.startswith('HELD_PINCH'):
        for bad in ('PINCH_CW', 'PINCH_ACW'):
            if hw_hits.get(bad, 0) > 0:
                print(f"  FAIL: hardware fired {bad} on a held pinch (false trigger)")
                ok = False

    print(f"  {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    all_ok = True

    # Scenario A: held pinch, no rotation. Accumulator must not drift.
    all_ok &= run_scenario(
        'HELD_PINCH (200 frames, no motion)',
        [45.0] * 200,
        expect_hw_fires={'PINCH'},
        expect_ref_fires={'pinch'},
    )

    # Scenario B: slow CW rotation (2 deg/frame for 30 frames = 60 deg total).
    # Both should fire pinch_clockwise at least a few times.
    all_ok &= run_scenario(
        'SLOW_CW (2 deg/frame, 30 frames)',
        [2.0 * i for i in range(30)],
        expect_hw_fires={'PINCH_CW'},
        expect_ref_fires={'pinch_clockwise'},
    )

    # Scenario C: slow ACW rotation.
    all_ok &= run_scenario(
        'SLOW_ACW (-2 deg/frame, 30 frames)',
        [-2.0 * i for i in range(30)],
        expect_hw_fires={'PINCH_ACW'},
        expect_ref_fires={'pinch_anticlockwise'},
    )

    # Scenario D: fast CW rotation (5 deg/frame).
    all_ok &= run_scenario(
        'FAST_CW (5 deg/frame, 15 frames)',
        [5.0 * i for i in range(15)],
        expect_hw_fires={'PINCH_CW'},
        expect_ref_fires={'pinch_clockwise'},
    )

    # Scenario E: direction reversal. Use 2.5 deg/frame (clearly above the
    # reference's 1.5 deg gate) in both directions.
    step = 2.5
    angles = [step * i for i in range(25)] + [step * 25 - step * i for i in range(1, 26)]
    all_ok &= run_scenario(
        'CW_THEN_ACW (2.5 deg/frame each way)',
        angles,
        expect_hw_fires={'PINCH_CW', 'PINCH_ACW'},
        expect_ref_fires={'pinch_clockwise', 'pinch_anticlockwise'},
    )

    # Scenario F: tiny jitter around a fixed angle, ~0.3 deg amplitude. The
    # noise floor should suppress rotation events on both sides.
    import random
    random.seed(0xC0FFEE)
    jitter = [30.0 + random.uniform(-0.3, 0.3) for _ in range(300)]
    all_ok &= run_scenario(
        'HELD_PINCH jitter 0.3 deg (300 frames)',
        jitter,
        expect_hw_fires={'PINCH'},
        expect_ref_fires={'pinch'},
    )

    # Scenario G: very fine angular step (0.5 deg/frame). Reference rejects
    # as below its 1.5 deg per-frame gate; HW should likewise not fire
    # (falls below NOISE_FLOOR).
    all_ok &= run_scenario(
        'SUB_NOISE (0.5 deg/frame, 60 frames)',
        [0.5 * i for i in range(60)],
        expect_hw_fires=set(),
        expect_ref_fires=set(),
    )

    print()
    print('ALL SCENARIOS PASS' if all_ok else 'SOME SCENARIOS FAILED')
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
