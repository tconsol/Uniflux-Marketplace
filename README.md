# Uniflux-Marketplace

## Deploy

The indeed scheduler runs in-process (APScheduler). Cloud Run must keep one
instance warm or the scheduler stops between ticks. Deploy with:

```
gcloud run deploy <marketplace-service> --source . --region asia-south1 --min-instances=1
```