FROM public.ecr.aws/lambda/python:3.12

# Work from Lambda task root
WORKDIR /var/task

# Copy the package into the task root
COPY app ./app

# Optional: verify contents at build time
# RUN ls -R

# The handler string is "<module>.<function>".
# Module is "app.handler", function is "handler".
CMD ["app.handler.handler"]