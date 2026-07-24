"""Ridge-orientation field via the structure tensor (modality-independent)."""
import cv2
import numpy as np


def orientation_field(gray, sigma_grad=1.5, sigma_tensor=8.0):
    g = gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    Jxx = cv2.GaussianBlur(gx * gx, (0, 0), sigma_tensor)
    Jyy = cv2.GaussianBlur(gy * gy, (0, 0), sigma_tensor)
    Jxy = cv2.GaussianBlur(gx * gy, (0, 0), sigma_tensor)
    theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy)                 # mod pi
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-6)
    return theta, coh
