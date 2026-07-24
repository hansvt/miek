"""Ridge-orientation utilities + validate a transform by orientation agreement."""
import cv2, numpy as np, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")


def orientation_field(gray, sigma_grad=1.5, sigma_tensor=8.0):
    g = gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    Jxx = cv2.GaussianBlur(gx * gx, (0, 0), sigma_tensor)
    Jyy = cv2.GaussianBlur(gy * gy, (0, 0), sigma_tensor)
    Jxy = cv2.GaussianBlur(gx * gy, (0, 0), sigma_tensor)
    theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy)   # ridge normal orientation, mod pi
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-6)
    return theta, coh


def load():
    oct_g = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
    imm_g = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))[:, :, 2]
    return oct_g, imm_g


def validate(A, t, n_samples=4000, coh_min=0.15):
    oct_g, imm_g = load()
    to, co = orientation_field(oct_g)
    ti, ci = orientation_field(imm_g)
    rot = np.arctan2(A[1, 0], A[0, 0])  # transform rotation
    Hh, Ww = imm_g.shape
    ys, xs = np.mgrid[0:oct_g.shape[0]:8, 0:oct_g.shape[1]:8]
    pts = np.stack([xs.ravel(), ys.ravel()], 1).astype(float)
    mapped = pts @ A.T + t
    diffs = []
    for (px, py), (mx, my) in zip(pts.astype(int), mapped):
        mxi, myi = int(round(mx)), int(round(my))
        if 0 <= mxi < Ww and 0 <= myi < Hh:
            if co[py, px] < coh_min or ci[myi, mxi] < coh_min:
                continue
            a = to[py, px] + rot            # OCT orientation after rotation
            b = ti[myi, mxi]
            d = (a - b) % np.pi
            d = min(d, np.pi - d)           # circular diff mod pi -> [0, pi/2]
            diffs.append(d)
    diffs = np.rad2deg(np.array(diffs))
    if len(diffs) == 0:
        return None
    return dict(n=len(diffs), mean=float(diffs.mean()), median=float(np.median(diffs)),
                frac_lt15=float((diffs < 15).mean()), frac_lt30=float((diffs < 30).mean()))


if __name__ == "__main__":
    d = np.load(os.path.join(OUT, "transform.npz"))
    A, t = d["A"], d["t"]
    print("rotation deg:", np.rad2deg(np.arctan2(A[1, 0], A[0, 0])))
    print(validate(A, t))
