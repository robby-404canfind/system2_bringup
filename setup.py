from setuptools import find_packages, setup
import os
from glob import glob

package_name = "system2_bringup"

setup(
    name=package_name,
    version="0.2.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
    ],
    install_requires=["setuptools", "pyyaml", "openai", "pydantic"],
    zip_safe=True,
    maintainer="student",
    maintainer_email="todo@todo.com",
    description="System2 LLM Planner 통합 패키지 (Physical AI 커리큘럼 Chapter 05)",
    license="MIT",
    entry_points={
        "console_scripts": [
            "system2_planner = system2_bringup.system2_planner_node:main",
        ],
    },
)
