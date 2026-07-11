# Shared marketplace constants.

# All marketplace job data lives in one global pool; the ScrapedJob.org_id field
# is retained for schema stability but always holds this sentinel. Subscription
# gating (who may VIEW the board) is enforced at the api-gateway, not here.
GLOBAL_ORG_ID = "GLOBAL"
