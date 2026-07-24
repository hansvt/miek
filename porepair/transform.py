"""Fit an OCT->immuno transform from corresponding landmark points.
Supports similarity (4 dof), affine (6 dof), and thin-plate-spline (tps).
Provides forward (oct->imm) and inverse (imm->oct) mapping for any kind."""
import numpy as np

try:
    from scipy.interpolate import RBFInterpolator
    _HAS_RBF = True
except Exception:                      # pragma: no cover
    _HAS_RBF = False


def _umeyama(src, dst, with_scale):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    Sc, Dc = src - mu_s, dst - mu_d
    U, D, Vt = np.linalg.svd(Dc.T @ Sc / len(src))
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1; R = U @ Vt
    s = (np.trace(np.diag(D)) / ((Sc ** 2).sum() / len(src))) if with_scale else 1.0
    A = s * R
    t = mu_d - A @ mu_s
    return A, t


def _affine(src, dst):
    X = np.hstack([src, np.ones((len(src), 1))])
    M, *_ = np.linalg.lstsq(X, dst, rcond=None)
    return M[:2].T, M[2]


class Transform:
    def __init__(self, kind, O, I):
        self.kind = kind
        O = np.asarray(O, float); I = np.asarray(I, float)
        self._O, self._I = O, I
        if kind in ("affine", "similarity"):
            if kind == "affine":
                A, t = _affine(O, I)
            else:
                A, t = _umeyama(O, I, True)
            self.A, self.t = A, t
            self.Ainv = np.linalg.inv(A)
            self._fwd = lambda p: p @ A.T + t
            self._inv = lambda p: (p - t) @ self.Ainv.T
        elif kind == "tps":
            if not _HAS_RBF:
                raise RuntimeError("tps requires scipy.interpolate.RBFInterpolator")
            self._rbf_fwd = RBFInterpolator(O, I, kernel="thin_plate_spline")
            self._rbf_inv = RBFInterpolator(I, O, kernel="thin_plate_spline")
            self._fwd = lambda p: self._rbf_fwd(p)
            self._inv = lambda p: self._rbf_inv(p)
            self.A, self.t = _affine(O, I)          # affine approx for image warp/backdrop
            self.Ainv = np.linalg.inv(self.A)
        else:
            raise ValueError(f"unknown transform kind {kind}")

    def apply(self, pts):        # oct -> imm
        return self._fwd(np.atleast_2d(np.asarray(pts, float)))

    def inverse(self, pts):      # imm -> oct
        return self._inv(np.atleast_2d(np.asarray(pts, float)))

    def residuals(self):
        pred = self.apply(self._O)
        return np.linalg.norm(pred - self._I, axis=1)

    def describe(self):
        d = self.residuals()
        info = {"kind": self.kind, "residual_mean_px": float(d.mean()),
                "residual_max_px": float(d.max()), "n_points": len(self._O)}
        A = self.A
        info["scale"] = float(np.sqrt(abs(np.linalg.det(A))))
        info["rotation_deg"] = float(np.rad2deg(np.arctan2(A[1, 0], A[0, 0])))
        sx = np.linalg.norm(A[:, 0]); sy = np.linalg.norm(A[:, 1])
        info["axis_angle_deg"] = float(np.rad2deg(np.arccos(np.clip((A[:, 0] @ A[:, 1]) / (sx * sy), -1, 1))))
        return info
