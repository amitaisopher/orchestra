export async function handler(event, context) {
  const start = Date.now();
  console.log("Lambda C");
  const delay = Math.floor(Math.random() * 10) + 1;
  await new Promise((r) => setTimeout(r, delay * 1000));
  const end = Date.now();
  return {
    functionName: context.functionName,
    requestId: context.awsRequestId,
    runtime: "nodejs18.x",
    task: "C",
    startTime: new Date(start).toISOString(),
    endTime: new Date(end).toISOString(),
    durationMs: end - start,
    delaySeconds: delay,
  };
}