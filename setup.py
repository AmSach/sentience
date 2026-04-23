from setuptools import setup, find_packages
setup(name="sentience",version="1.0.0",packages=find_packages(),install_requires=["flask","flask-cors","anthropic","openai","groq","python-dotenv","lz4","playwright","pyyaml"],scripts=["sentience.py"],description="Sentience - Local AI Computer",author="man44")
