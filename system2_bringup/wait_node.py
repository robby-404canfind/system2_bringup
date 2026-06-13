"""wait_node.py — wait() Unit Action helper.

Ch03에서는 순수 함수형 helper만 구현합니다.
ROS2 노드는 status_callback으로 /system2/status에 연결합니다.
"""
import time


def exec_wait(seconds: int, status_callback=None) -> bool:
    """wait Unit Action 실행.

    Args:
        seconds: 대기 시간 (초).
        status_callback: 상태 발행 콜백.

    Returns:
        True (항상 성공).
    """
    cb = status_callback or (lambda msg: print(f"[wait] {msg}"))
    cb(f"waiting {seconds}s...")
    time.sleep(seconds)
    cb(f"wait complete ({seconds}s)")
    return True
