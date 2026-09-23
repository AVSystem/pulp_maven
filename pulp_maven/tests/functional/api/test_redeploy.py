"""Re-publishing the same coordinates with different content."""

import hashlib

import requests

from pulp_maven.tests.functional.utils import download_file

ARTIFACT_PATH = "com/example/redeploy/1.0.0-SNAPSHOT/redeploy-1.0.0-SNAPSHOT.jar"
FIRST = b"first build of this snapshot"
SECOND = b"second build of this snapshot, different bytes"


def _deploy_url(pulp_settings, repo_name, path=ARTIFACT_PATH):
    base = pulp_settings.CONTENT_ORIGIN.rstrip("/")
    if pulp_settings.DOMAIN_ENABLED:
        return f"{base}/pulp/maven/default/{repo_name}/{path}"
    return f"{base}/pulp/maven/{repo_name}/{path}"


def _content_url(distribution, path=ARTIFACT_PATH):
    return f"{distribution.base_url.rstrip('/')}/{path}"


def test_redeploy_with_new_content_serves_the_new_content(
    maven_repo_api_client, maven_repo_factory, maven_distribution_factory, pulp_settings
):
    """A second deploy to the same coordinates must not leave the first file in place.

    Snapshot development republishes the same coordinates repeatedly. Keeping the
    original file while answering the upload with a success status makes that
    workflow fail silently: the publisher is told the build was uploaded, and
    everyone downstream keeps resolving the previous one.
    """
    repo = maven_repo_factory()
    distribution = maven_distribution_factory(repository=repo.pulp_href)
    url = _deploy_url(pulp_settings, repo.name)

    assert requests.put(url, data=FIRST, verify=False).status_code == 201
    downloaded = download_file(_content_url(distribution))
    assert hashlib.sha256(downloaded.body).hexdigest() == hashlib.sha256(FIRST).hexdigest()

    assert requests.put(url, data=SECOND, verify=False).status_code == 201
    downloaded = download_file(_content_url(distribution))
    assert hashlib.sha256(downloaded.body).hexdigest() == hashlib.sha256(SECOND).hexdigest()


def test_redeploy_of_identical_content_does_not_create_a_repository_version(
    maven_repo_api_client, maven_repo_factory, maven_distribution_factory, pulp_settings
):
    """Re-uploading the same bytes stays a no-op.

    A build that deploys unchanged output should not accumulate repository
    versions, which is why the checksum is what distinguishes one upload from
    another rather than the upload simply always replacing.
    """
    repo = maven_repo_factory()
    maven_distribution_factory(repository=repo.pulp_href)
    url = _deploy_url(pulp_settings, repo.name)

    assert requests.put(url, data=FIRST, verify=False).status_code == 201
    first_version = maven_repo_api_client.read(repo.pulp_href).latest_version_href

    assert requests.put(url, data=FIRST, verify=False).status_code == 201
    assert maven_repo_api_client.read(repo.pulp_href).latest_version_href == first_version


def test_redeployed_repository_holds_one_artifact_per_coordinate(
    maven_repo_api_client,
    maven_artifact_api_client,
    maven_repo_factory,
    maven_distribution_factory,
    pulp_settings,
):
    """The superseded file must leave the repository rather than sit alongside it.

    Two units for one path in the same repository version would make what gets
    served depend on ordering. Both units still exist as content -- they are
    distinct by checksum -- but only the newer one belongs to the repository.
    """
    repo = maven_repo_factory()
    maven_distribution_factory(repository=repo.pulp_href)
    url = _deploy_url(pulp_settings, repo.name)

    requests.put(url, data=FIRST, verify=False)
    requests.put(url, data=SECOND, verify=False)

    latest = maven_repo_api_client.read(repo.pulp_href).latest_version_href

    in_repository = maven_artifact_api_client.list(
        repository_version=latest, filename="redeploy-1.0.0-SNAPSHOT.jar"
    )
    assert in_repository.count == 1
    assert in_repository.results[0].sha256 == hashlib.sha256(SECOND).hexdigest()

    everywhere = maven_artifact_api_client.list(filename="redeploy-1.0.0-SNAPSHOT.jar")
    assert everywhere.count == 2
