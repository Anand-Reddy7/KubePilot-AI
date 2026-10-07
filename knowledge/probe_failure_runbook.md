# Kubernetes Probe Failure Troubleshooting

## Symptoms

A pod is Running but Kubernetes reports readiness or liveness probe failures.

The Service may stop routing traffic to the pod when readiness checks fail.

## Investigation

Describe the pod and inspect events:

kubectl describe pod <pod-name> -n <namespace>

Check application logs.

Verify the configured probe path, port, timeout and initial delay.

## Common Causes

- Incorrect HTTP probe path.
- Incorrect container port.
- Application startup takes longer than initialDelaySeconds.
- Probe timeout is too short.
- Application is unhealthy.

## Remediation

Correct the probe configuration only after verifying the application's actual health endpoint and startup behavior.

## Verification

Check pod readiness:

kubectl get pods -n <namespace>

Confirm that readiness becomes true and probe failure events stop.