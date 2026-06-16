"""Stockage médias S3 / Cloudflare R2 (bucket privé, accès via URLs signées applicatives)."""

from storages.backends.s3boto3 import S3Boto3Storage


class FotoceMediaStorage(S3Boto3Storage):
    default_acl = 'private'
    file_overwrite = False
    querystring_auth = False
