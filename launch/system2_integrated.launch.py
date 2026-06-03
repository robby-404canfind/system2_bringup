"""system2_integrated.launch.py - Ch05 System2 planner/action launch.

Perception ActionServer와 System2 Planner를 실행합니다.
시뮬레이션(Webots + Nav2)은 컨테이너 내부에서 별도로 시작합니다.
YOLO detector와 perception context builder까지 함께 실행하려면
system2_full_stack.launch.py 또는 agentic_vla_system.launch.py를 사용합니다.

실행 순서:
  1) hunavbash
     ros2 launch hunav_webots_wrapper hunavsim_webots.launch.py \
       environment_name:=hall \
       configuration_file:=agents_hall.yaml
  2) ros2 launch system2_bringup system2_full_stack.launch.py
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
            # system2_full_stack.launch.py에서 YOLO + Context Builder와 함께 포함됨
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
