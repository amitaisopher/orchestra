FROM public.ecr.aws/lambda/python:3.12

# Install any deps (none required for this simple demo)
# RUN pip install -r requirements.txt

# Copy function code
COPY app /var/task

# Command is handler in app/handler.py
CMD ["app.handler.handler"]