# Kubernetes Pending Pod Troubleshooting

## Symptoms

A pod remains in Pending state and is not scheduled to a node.

## Investigation

Check the pod:

kubectl get pods -n <namespace>

Describe the pod:

kubectl describe pod <pod-name> -n <namespace>

Review scheduling events.

Check nodes:

kubectl get nodes

Check resource availability:

kubectl top nodes

## Common Causes

- Insufficient CPU.
- Insufficient memory.
- Node selector mismatch.
- Taints without matching tolerations.
- PersistentVolumeClaim unavailable.
- Pod affinity or anti-affinity restrictions.

## Remediation

Identify the scheduler reason from Kubernetes events.

Do not modify scheduling constraints or resource requests automatically without validating the workload requirements.

## Verification

Confirm that the pod is scheduled and transitions to Running.