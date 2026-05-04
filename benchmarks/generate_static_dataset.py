"""
Creates a reproducible, static set of synthetic 21-landmark hand-pose
vectors for use by benchmark_classifier_efficacy.py.

Four gesture classes shared by BOTH pipelines:
    fist | open_palm | index_finger | pinch

Each sample stores:
  - pixel-space landmarks  [[id, x, y], ...]        → software classifier
  - uint16-normalised landmarks [{id, nx, ny}, ...]  → FPGA reference check
  - 105-byte UART frame    [int, ...]                → live FPGA path

Usage
-----
    python generate_static_dataset.py [--samples-per-class 50] [--noise 4.0] [--seed 42]
"""

import argparse, copy, json, os, random

# Canonical templates  (640×480 image, Y increases downward, wrist ~(320,380))

OPEN_PALM_BASE = [
    [0,320,380],[1,295,360],[2,275,338],[3,258,314],[4,244,290],
    [5,305,328],[6,302,292],[7,300,260],[8,299,228],
    [9,320,323],[10,320,285],[11,320,251],[12,320,217],
    [13,335,328],[14,338,293],[15,340,260],[16,342,228],
    [17,350,336],[18,355,306],[19,358,278],[20,360,251],
]

FIST_BASE = [
    [0,320,380],[1,300,358],[2,282,340],[3,285,358],[4,295,372],
    [5,305,325],[6,310,345],[7,318,358],[8,322,368],
    [9,320,322],[10,325,342],[11,330,356],[12,333,366],
    [13,335,326],[14,340,344],[15,344,358],[16,347,368],
    [17,350,335],[18,354,350],[19,357,362],[20,359,371],
]

INDEX_FINGER_BASE = [
    [0,320,380],[1,300,358],[2,282,340],[3,285,358],[4,295,372],
    [5,305,325],[6,303,290],[7,301,258],[8,300,226],
    [9,320,322],[10,325,342],[11,330,356],[12,333,366],
    [13,335,326],[14,340,344],[15,344,358],[16,347,368],
    [17,350,335],[18,354,350],[19,357,362],[20,359,371],
]

PINCH_BASE = [
    [0,320,380],[1,300,360],[2,282,342],[3,290,322],[4,308,308],
    [5,305,325],[6,308,305],[7,310,315],[8,312,312],
    [9,320,322],[10,325,342],[11,330,356],[12,333,366],
    [13,335,326],[14,340,344],[15,344,358],[16,347,368],
    [17,350,335],[18,354,350],[19,357,362],[20,359,371],
]

TEMPLATES = {
    "open_palm":    OPEN_PALM_BASE,
    "fist":         FIST_BASE,
    "index_finger": INDEX_FINGER_BASE,
    "pinch":        PINCH_BASE,
}

FPGA_LABEL_MAP = {"pinch":0,"fist":1,"open_palm":2,"index_finger":3,
                  "unknown":4,"pinch_cw":5,"pinch_acw":6}


def _noisy(template, sigma, rng):
    t = copy.deepcopy(template)
    for lm in t:
        lm[1] += int(rng.gauss(0, sigma))
        lm[2] += int(rng.gauss(0, sigma))
    return t


def _norm(landmarks):
    s = sorted(landmarks, key=lambda l: l[0])
    wx, wy = s[0][1], s[0][2]
    md = max((max(abs(l[1]-wx), abs(l[2]-wy)) for l in s), default=1) or 1
    return [{"id":l[0],
             "nx": max(0,min(65535,int(((l[1]-wx)/md+1)*32767))),
             "ny": max(0,min(65535,int(((l[2]-wy)/md+1)*32767)))}
            for l in s]


def _frame(landmarks):
    s = sorted(landmarks, key=lambda l: l[0])
    wx, wy = s[0][1], s[0][2]
    md = max((max(abs(l[1]-wx), abs(l[2]-wy)) for l in s), default=1) or 1
    out = []
    for l in s:
        nx = max(0,min(65535,int(((l[1]-wx)/md+1)*32767)))
        ny = max(0,min(65535,int(((l[2]-wy)/md+1)*32767)))
        out += [l[0]&0x1F,(nx>>8)&0xFF,nx&0xFF,(ny>>8)&0xFF,ny&0xFF]
    return out  # 105 bytes


def generate(n, sigma, seed):
    rng = random.Random(seed)
    samples = []
    for label, tmpl in TEMPLATES.items():
        for i in range(n):
            lm = _noisy(tmpl, sigma, rng)
            samples.append({
                "sample_id":        f"{label}_{i:04d}",
                "true_label":       label,
                "fpga_true_id":     FPGA_LABEL_MAP[label],
                "landmarks_px":     lm,
                "landmarks_norm":   _norm(lm),
                "uart_frame_bytes": _frame(lm),
            })
    rng.shuffle(samples)
    return {
        "metadata": {
            "samples_per_class": n, "noise_sigma_px": sigma, "seed": seed,
            "frame_size": [640,480], "classes": list(TEMPLATES.keys()),
            "fpga_label_map": FPGA_LABEL_MAP,
        },
        "samples": samples,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples-per-class", type=int, default=50)
    ap.add_argument("--noise", type=float, default=4.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__),"data"))
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    out = os.path.join(args.out_dir, "static_gesture_dataset.json")
    ds = generate(args.samples_per_class, args.noise, args.seed)
    with open(out,"w") as f:
        json.dump(ds, f, indent=2)
    print(f"Generated {len(ds['samples'])} samples → {out}")

if __name__ == "__main__":
    main()
