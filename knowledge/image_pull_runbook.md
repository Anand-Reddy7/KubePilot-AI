# Kubernetes Image Pull Troubleshooting Runbook

## ImagePullBackOff and ErrImagePull

### Symptoms

A Kubernetes pod may remain in one of these states:

- ImagePullBackOff
- ErrImagePull

The application container does not start because Kubernetes cannot
download the configured container image.

### Possible Causes

Common causes include:

- Incorrect container image name
- Incorrect image tag
- Container image does not exist
- Private registry authentication failure
- Missing or incorrect imagePullSecrets
- Registry connectivity problems

### Troubleshooting Procedure

1. Check the pod status.

2. Review Kubernetes events for the affected pod.

3. Inspect the container image configured in the Deployment.

4. Verify that the image name and tag are correct.

5. Verify that the image exists in the configured container registry.

6. If using a private registry, verify that the required
   imagePullSecret exists in the namespace.

7. Verify that the Deployment references the correct imagePullSecret.

8. After correcting the image configuration, update the Deployment.

9. Verify that Kubernetes successfully pulls the image.

10. Confirm that the new pod reaches Running and Ready state.

### Example Remediation

If the Deployment contains an incorrect image:

    containers:
      - name: broken-app
        image: nginx:this-tag-does-not-exist

Update it to a valid image:

    containers:
      - name: broken-app
        image: nginx:1.27

Then apply the corrected Deployment and verify the rollout.

### Safety

Do not repeatedly delete or restart the pod without identifying why
the image cannot be pulled.

Restarting a pod does not fix an invalid image name, invalid image tag,
registry authentication problem, or missing imagePullSecret.