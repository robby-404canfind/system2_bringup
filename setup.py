from setuptools import find_packages, setup
import os
from glob import glob

package_name = "system2_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools", "pyyaml", "openai", "pydantic"],
    zip_safe=True,
    maintainer="Robby",
    maintainer_email="robby.404canfind@gmail.com",
    description="System2 LLM Planner 실습 패키지 (Physical AI 커리큘럼 Chapter 03)",
    license="MIT",
    entry_points={
        "console_scripts": [
            "system2_planner = system2_bringup.system2_planner_node:main",
        ],
    },
)
