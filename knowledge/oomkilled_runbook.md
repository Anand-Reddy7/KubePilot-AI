# Kubernetes OOMKilled Troubleshooting

## Symptoms

A container terminates with reason OOMKilled.
The pod may enter CrashLoopBackOff when the application repeatedly exceeds its memory limit.

## Investigation

Check pod status:

kubectl get pods -n <namespace>

Describe the pod:

kubectl describe pod <pod-name> -n <namespace>

Check the previous termination reason and exit code.

kubectl get pod <pod-name> -n <namespace> -o yaml

Review memory requests and limits.

kubectl top pod <pod-name> -n <namespace>

## Common Causes

- Container memory limit is too low.
- Application memory leak.
- JVM or runtime memory configuration exceeds the container limit.
- Unexpected workload or traffic increase.

## Remediation

Determine whether the application is consuming abnormal memory.

If memory usage is expected, increase the Deployment memory limit.

Do not automatically increase production resource limits without approval.

## Verification

Verify that the replacement pod becomes Running and remains stable.

Check:

kubectl get pods -n <namespace>

Review restart count and memory usage.