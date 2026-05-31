"""system2_integrated.launch.py — Ch05 통합 Launch.

Ch04 Perception 스택 + Perception ActionServer + System2 Planner를 실행합니다.
시뮬레이션(Webots + Nav2)은 HuNavSim Docker 메뉴에서 별도로 시작합니다.

실행 순서:
  1) HuNavSim Docker: ./run-hunav_webots.bash → agents_office.yaml 선택
  2) Perception 스택: ros2 launch perception_bringup perception.launch.py
  3) 이 launch 파일: ros2 launch system2_bringup system2_integrated.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    system2_share = get_package_share_directory("system2_bringup")
    perception_share = get_package_share_directory("perception_bringup")
    config_dir = os.path.join(system2_share, "config")
    perception_config = os.path.join(
        perception_share, "config", "perception_config.yaml"
    )

    return LaunchDescription(
        [
            # ---- Launch Arguments ----
            DeclareLaunchArgument(
                "backend",
                default_value="",
                description="LLM backend override (빈 값이면 llm_config.yaml 사용)",
            ),
            DeclareLaunchArgument(
                "model",
                default_value="",
                description="LLM model override (빈 값이면 llm_config.yaml 사용)",
            ),
            DeclareLaunchArgument(
                "go_home_location",
                default_value="charging_station",
                description="Fallback 귀환 위치",
            ),
            # ---- Ch04/Ch05 Perception Action Servers ----
            # perception.launch.py는 별도 실행 (YOLO + VLM Context Builder)
            # 여기서는 find/scan/follow와 assess_scene/resolve_target ActionServer를 실행
            Node(
                package="perception_bringup",
                executable="find_node",
                name="find_action_server",
                output="screen",
            ),
            Node(
                package="perception_bringup",
                executable="scan_node",
                name="scan_action_server",
                output="screen",
            ),
            Node(
                package="perception_bringup",
                executable="follow_node",
                name="follow_action_server",
                output="screen",
            ),
            Node(
                package="perception_bringup",
                executable="assess_scene_node",
                name="assess_scene_action_server",
                parameters=[perception_config],
                output="screen",
            ),
            Node(
                package="perception_bringup",
                executable="resolve_target_node",
                name="resolve_target_action_server",
                parameters=[perception_config],
                output="screen",
            ),
            # ---- Ch05 System2 Planner ----
            Node(
                package="system2_bringup",
                executable="system2_planner",
                name="system2_planner",
                parameters=[
                    {
                        "config_dir": config_dir,
                        "backend": LaunchConfiguration("backend"),
                        "model": LaunchConfiguration("model"),
                        "go_home_location": LaunchConfiguration(
                            "go_home_location"
                        ),
                    }
                ],
                output="screen",
            ),
        ]
    )
