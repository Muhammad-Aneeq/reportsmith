FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY numcheck ./numcheck
# Dependencies first, so a source edit does not invalidate the dependency layer.
RUN uv pip install --system -e "." 2>/dev/null || pip install --no-cache-dir \
    "fastapi>=0.141,<1.0" "uvicorn[standard]>=0.34" "pydantic>=2.13,<3.0" \
    "pydantic-settings>=2.7" "sqlalchemy>=2.0.52,<3.0" "pyyaml>=6.0.3" \
    "reportlab>=5.0.1,<6.0" "langgraph>=1.2.11,<2.0" "langchain-core>=1.6.1,<2.0" \
    "langchain-openai>=1.6.0,<2.0" "python-multipart>=0.0.20"

COPY app ./app
COPY ledgerfab ./ledgerfab

ENV PYTHONPATH=/app:/app/numcheck REPORTSMITH_LLM=mock
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
