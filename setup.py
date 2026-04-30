from setuptools import setup, find_packages

setup(
    name="sentience",
    version="2.0.0",
    packages=find_packages(),
    py_modules=["cli", "spawn_agents", "__main__"],  # Root-level .py files
    install_requires=[
        "flask>=3.0.0",
        "flask-cors>=4.0.0",
        "anthropic>=0.18.0",
        "openai>=1.0.0",
        "groq>=0.4.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "requests>=2.31.0",
        "pypdf>=3.0.0",
        "reportlab>=4.0.0",
        "python-docx>=1.0.0",
        "openpyxl>=3.1.0",
        "lz4>=4.0.0",
        "playwright>=1.40.0",
        "psutil>=5.9.0",
        "watchdog>=3.0.0",
    ],
    extras_require={
        "gui": ["PySide6>=6.6.0"],
        "all": ["PySide6>=6.6.0", "pillow>=10.0.0", "pytesseract>=0.3.10"],
    },
    entry_points={
        "console_scripts": [
            "sentience=cli:main",  # FIXED: cli is at root, not in sentience/ package
        ],
    },
)