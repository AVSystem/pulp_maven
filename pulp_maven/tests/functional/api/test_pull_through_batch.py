"""Files pulled through a remote, added to the repository in batches (MAVEN_PULL_THROUGH_BATCH)."""

import hashlib
import time
from urllib.parse import urljoin

import pytest

from pulp_maven.tests.functional.utils import download_file

REMOTE_URL = "https://repo1.maven.org/maven2/"
DIRECTORY = "academy/alex/custommatcher/1.0/"
FILES = [
    "custommatcher-1.0-javadoc.jar.sha1",
    "custommatcher-1.0-sources.jar.sha1",
    "custommatcher-1.0.jar.sha1",
    "custommatcher-1.0.pom.sha1",
    "custommatcher-1.0.jar.md5",
]


@pytest.fixture(autouse=True)
def _batch_mode_only(pulp_settings):
    if not pulp_settings.MAVEN_PULL_THROUGH_BATCH:
        pytest.skip("The server does not batch pull-through (MAVEN_PULL_THROUGH_BATCH is off).")


def _committed(pulp_settings):
    """Seconds after the first file within which its batch is committed, with room to spare.

    The window, plus the time the workers take to notice a due schedule and run the commit.
    """
    return pulp_settings.MAVEN_PULL_THROUGH_BATCH_WINDOW + 40


def _version_number(maven_repo_api_client, repo):
    href = maven_repo_api_client.read(repo.pulp_href).latest_version_href
    return int(href.rstrip("/").rsplit("/", 1)[1])


def _wait_for_version(maven_repo_api_client, repo, number, timeout):
    deadline = time.monotonic() + timeout
    while _version_number(maven_repo_api_client, repo) < number:
        assert time.monotonic() < deadline, "the pulled-through files were not committed in time"
        time.sleep(1)


@pytest.fixture
def pull_through(
    maven_remote_factory,
    maven_repo_factory,
    maven_distribution_factory,
    distribution_base_url,
):
    remote = maven_remote_factory(url=REMOTE_URL)
    repo = maven_repo_factory(remote=remote.pulp_href)
    distribution = maven_distribution_factory(remote=remote.pulp_href, repository=repo.pulp_href)
    base_url = distribution_base_url(distribution.base_url)

    def _fetch(name):
        return download_file(urljoin(base_url, DIRECTORY + name))

    return repo, distribution, _fetch


def test_pulled_through_files_share_one_version(
    pull_through, maven_repo_api_client, maven_artifact_api_client, pulp_settings
):
    """Files fetched through the remote within one window land in a single new version."""
    repo, _, fetch = pull_through
    bodies = {}
    for name in FILES:
        downloaded = fetch(name)
        assert downloaded.response_obj.status == 200
        bodies[name] = hashlib.sha256(downloaded.body).hexdigest()

    # Nothing is committed while the window is open.
    assert _version_number(maven_repo_api_client, repo) == 0

    _wait_for_version(maven_repo_api_client, repo, 1, _committed(pulp_settings))
    # Allow a stray second version to show up before checking there is none.
    time.sleep(5)
    assert _version_number(maven_repo_api_client, repo) == 1
    href = maven_repo_api_client.read(repo.pulp_href).latest_version_href
    in_version = {
        a.filename
        for a in maven_artifact_api_client.list(repository_version=href, limit=100).results
    }
    assert set(FILES) <= in_version

    for name in FILES:
        assert hashlib.sha256(fetch(name).body).hexdigest() == bodies[name]


def test_pending_files_are_served_without_the_remote(
    pull_through, maven_repo_api_client, maven_distro_api_client, monitor_task, pulp_settings
):
    """A file waiting for its batch is served from Pulp, not fetched from the remote again."""
    repo, distribution, fetch = pull_through
    name = FILES[0]
    expected = hashlib.sha256(fetch(name).body).hexdigest()
    assert _version_number(maven_repo_api_client, repo) == 0

    monitor_task(
        maven_distro_api_client.partial_update(distribution.pulp_href, {"remote": None}).task
    )
    pending = fetch(name)
    assert pending.response_obj.status == 200
    assert hashlib.sha256(pending.body).hexdigest() == expected
    assert _version_number(maven_repo_api_client, repo) == 0

    _wait_for_version(maven_repo_api_client, repo, 1, _committed(pulp_settings))
    committed = fetch(name)
    assert committed.response_obj.status == 200
    assert hashlib.sha256(committed.body).hexdigest() == expected


def test_a_file_fetched_again_is_recorded_once(
    pull_through, maven_repo_api_client, maven_artifact_api_client, pulp_settings
):
    """Fetching a pending file again does not add it twice."""
    repo, _, fetch = pull_through
    name = FILES[1]
    for _ in range(3):
        assert fetch(name).response_obj.status == 200

    _wait_for_version(maven_repo_api_client, repo, 1, _committed(pulp_settings))
    href = maven_repo_api_client.read(repo.pulp_href).latest_version_href
    assert maven_artifact_api_client.list(repository_version=href, filename=name).count == 1
