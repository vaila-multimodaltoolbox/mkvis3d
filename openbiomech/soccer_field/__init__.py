"""Soccer-field keypoint dataset tooling (kiki 49-point layout).

Auxiliary to the biomechanics prototype: builds a YOLO-Pose dataset whose 49
keypoints follow vailá ``models/soccerfield_kiki.csv`` (metric FIFA pitch,
centred origin, x along the length, y towards the far touchline, z up).
The dataset is consumed later by vailá for training and video tracking.
"""
