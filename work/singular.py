"""Detect singular points (core=+1/2, delta=-1/2) via the Poincare index on the
ridge-orientation field. These are unique, modality-invariant anchors."""
import cv2, numpy as np, os
from orient import orientation_field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")


def poincare(theta, coh, mask, block=12, coh_min=0.25):
    H, W = theta.shape
    # angle doubled to handle pi-periodicity; work on a coarse grid
    idx_map = np.zeros((H, W), np.float32)
    r = block
    ys = range(r, H - r, max(1, block // 2))
    xs = range(r, W - r, max(1, block // 2))
    loop = []
    for dx, dy in [(-r, -r), (0, -r), (r, -r), (r, 0), (r, r), (0, r), (-r, r), (-r, 0)]:
        loop.append((dx, dy))
    cores, deltas = [], []
    for y in ys:
        for x in xs:
            if mask[y, x] == 0 or coh[y, x] < coh_min:
                continue
            angs = [theta[y + dy, x + dx] for (dx, dy) in loop]
            s = 0.0
            for i in range(len(angs)):
                d = angs[(i + 1) % len(angs)] - angs[i]
                # wrap into (-pi/2, pi/2] because orientation is mod pi
                while d <= -np.pi / 2:
                    d += np.pi
                while d > np.pi / 2:
                    d -= np.pi
                s += d
            pi_idx = s / np.pi  # ~ +0.5 core, -0.5 delta
            if pi_idx > 0.35:
                cores.append((x, y, pi_idx))
            elif pi_idx < -0.35:
                deltas.append((x, y, pi_idx))
    return cores, deltas


def cluster(points, rad=40):
    """merge nearby detections, weight by |index|"""
    pts = np.array([(p[0], p[1]) for p in points], float)
    if len(pts) == 0:
        return []
    used = np.zeros(len(pts), bool)
    out = []
    for i in range(len(pts)):
        if used[i]:
            continue
        near = np.where(np.hypot(*(pts - pts[i]).T) < rad)[0]
        used[near] = True
        out.append((pts[near].mean(0), len(near)))
    out.sort(key=lambda z: -z[1])
    return out


def analyze(gray, mask, name):
    th, coh = orientation_field(gray, 1.5, 12.0)
    cores, deltas = poincare(th, coh, mask, block=14)
    cc = cluster(cores); dd = cluster(deltas)
    print(f"\n{name}: {len(cores)} core-votes -> {len(cc)} clusters; {len(deltas)} delta-votes -> {len(dd)} clusters")
    for (p, n) in cc[:4]:
        print(f"   CORE  ~({p[0]:.0f},{p[1]:.0f}) votes={n}")
    for (p, n) in dd[:4]:
        print(f"   DELTA ~({p[0]:.0f},{p[1]:.0f}) votes={n}")
    vis = cv2.cvtColor(cv2.createCLAHE(3.0, (16, 16)).apply(gray), cv2.COLOR_GRAY2BGR)
    for (p, n) in cc[:4]:
        cv2.circle(vis, (int(p[0]), int(p[1])), 22, (0, 0, 255), 3)
        cv2.putText(vis, f"C{n}", (int(p[0]) + 10, int(p[1])), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    for (p, n) in dd[:4]:
        cv2.circle(vis, (int(p[0]), int(p[1])), 22, (255, 0, 0), 3)
        cv2.putText(vis, f"D{n}", (int(p[0]) + 10, int(p[1])), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
    return vis, cc, dd


octg = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
octm = (octg > 25).astype(np.uint8); octm = cv2.erode(octm, np.ones((45, 45), np.uint8))
immr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))[:, :, 2]
blur = cv2.GaussianBlur(immr, (0, 0), 25); m = (blur > np.percentile(blur, 85)).astype(np.uint8)
n, lab, st, _ = cv2.connectedComponentsWithStats(m); big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
immm = (lab == big).astype(np.uint8); immm = cv2.morphologyEx(immm, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
immm = cv2.erode(immm, np.ones((45, 45), np.uint8))

vo, oc, od = analyze(octg, octm, "OCT")
vi, ic, idd = analyze(immr, immm, "IMM")
cv2.imwrite(os.path.join(OUT, "oct_singular.png"), vo)
# crop immuno
ys, xs = np.where(immm > 0)
cv2.imwrite(os.path.join(OUT, "imm_singular.png"), vi[max(0,ys.min()-40):ys.max()+40, max(0,xs.min()-40):xs.max()+40])
np.savez(os.path.join(OUT, "singular.npz"),
         oct_core=np.array([p for p, _ in oc[:3]]), oct_delta=np.array([p for p, _ in od[:3]]),
         imm_core=np.array([p for p, _ in ic[:3]]), imm_delta=np.array([p for p, _ in idd[:3]]))
print("\nwrote oct_singular.png, imm_singular.png, singular.npz")
