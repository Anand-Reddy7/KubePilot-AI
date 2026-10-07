# Kubernetes Application Troubleshooting Runbook

## Application Startup Failure Due to Missing Environment Variable

### Symptoms

The application pod may repeatedly restart and eventually enter
CrashLoopBackOff.

Application logs may contain messages similar to:

ERROR: Required environment variable is missing

The container may terminate with a non-zero exit code.

### Possible Cause

The application requires an environment variable that has not been
configured in the Kubernetes Deployment.

The required value may normally come directly from the Deployment,
a ConfigMap, or a Kubernetes Secret.

### Troubleshooting Procedure

1. Check the pod status and restart count.

2. Review the application container logs.

3. Identify the missing environment variable from the error message.

4. Inspect the Kubernetes Deployment configuration.

5. Check whether the environment variable should come from:
   - Deployment environment configuration
   - ConfigMap
   - Kubernetes Secret

6. Verify that the referenced ConfigMap or Secret exists in the
   application's namespace.

7. Update the Deployment with the required environment variable.

8. Apply the updated Deployment.

9. Wait for Kubernetes to create the new pod.

10. Verify that the new pod reaches Running and Ready state.

11. Review the application logs to confirm successful startup.

### Example Remediation

If APP_CONFIG is required, configure it in the Deployment.

Example:

    env:
      - name: APP_CONFIG
        value: "production"

After updating the Deployment, apply the configuration and verify
the rollout.

### Safety

Do not blindly restart a CrashLoopBackOff pod without identifying
the underlying configuration problem.

A restart alone will not resolve a missing environment variable.

Validate configuration changes before applying them to production
workloads.