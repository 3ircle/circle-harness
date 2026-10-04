import os
import re
import stat
import shutil
import subprocess
from typing import Optional, Dict, Any, List


def safe_rmtree(target_path: str):
    """
    Safely removes a directory tree on Windows, stripping read-only file attributes
    to prevent PermissionError / WinError 5 on Git pack and index files.
    """
    if not os.path.exists(target_path):
        return

    def _remove_readonly(func, path, _):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)
        except Exception:
            pass

    import sys
    if sys.version_info >= (3, 12):
        def _on_exc(func, path, _):
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                func(path)
            except Exception:
                pass
        try:
            shutil.rmtree(target_path, on_exc=_on_exc)
        except TypeError:
            shutil.rmtree(target_path, onerror=_remove_readonly)
    else:
        shutil.rmtree(target_path, onerror=_remove_readonly)


class WorktreeManager:
    """
    Manages isolated Git worktrees for Circle Harness sessions, matching the Claude Code worktree paradigm.
    Creates isolated checkouts under <repo>/.circle/worktrees/<session_id> on branch circle/session-<session_id[:8]>.
    """

    def __init__(self, repo_path: str, session_id: str, base_ref: str = "HEAD"):
        self.repo_path = os.path.abspath(os.path.normpath(repo_path))
        self.session_id = session_id
        self.sanitized_id = re.sub(r"[^a-zA-Z0-9_\-]", "", session_id) or "default"
        self.short_id = self.sanitized_id[:8]
        self.branch_name = f"circle/session-{self.short_id}"
        self.base_ref = base_ref or "HEAD"
        self.worktree_dir = os.path.join(self.repo_path, ".circle", "worktrees", self.sanitized_id)

    def _run_git(self, args: List[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
        target_cwd = cwd or self.repo_path
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"

        # Provide fallback author identity for seamless automated worktree commits
        base_cmd = [
            "git",
            "-c", "core.quotepath=false",
            "-c", "user.name=Circle Harness",
            "-c", "user.email=harness@circle.local"
        ]
        cmd = base_cmd + args

        return subprocess.run(
            cmd,
            cwd=target_cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )

    def is_git_repo(self) -> bool:
        """Returns True if repo_path is inside a valid git working tree."""
        if not os.path.exists(self.repo_path):
            return False
        res = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return res.returncode == 0 and res.stdout.strip() == "true"

    def ensure_gitignore_configured(self) -> bool:
        """
        Ensures .circle/ is present in .gitignore and .git/info/exclude
        so worktrees are never committed or tracked in the main repository.
        """
        try:
            # 1. Update .gitignore
            gitignore_path = os.path.join(self.repo_path, ".gitignore")
            needs_append = True
            if os.path.exists(gitignore_path):
                with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if re.search(r"^\.circle/?$", content, flags=re.MULTILINE):
                    needs_append = False

            if needs_append:
                prefix = "\n" if (os.path.exists(gitignore_path) and os.path.getsize(gitignore_path) > 0) else ""
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    f.write(f"{prefix}# Circle Harness isolated worktree workspace\n.circle/\n")

            # 2. Local git exclude fallback
            git_info_exclude = os.path.join(self.repo_path, ".git", "info", "exclude")
            if os.path.exists(os.path.dirname(git_info_exclude)):
                with open(git_info_exclude, "a", encoding="utf-8") as f:
                    f.write("\n.circle/\n")

            return True
        except Exception:
            return False

    def create_worktree(self, base_ref: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates an isolated linked git worktree under .circle/worktrees/<session_id>.
        Returns metadata dict with worktree path and branch.
        """
        if not self.is_git_repo():
            return {
                "success": False,
                "error": f"Path '{self.repo_path}' is not a valid Git repository."
            }

        self.ensure_gitignore_configured()
        ref = base_ref or self.base_ref or "HEAD"

        # Check if worktree directory already exists and is active
        if os.path.exists(self.worktree_dir):
            list_res = self._run_git(["worktree", "list", "--porcelain"])
            if self.worktree_dir in list_res.stdout:
                return {
                    "success": True,
                    "reused": True,
                    "worktree_path": self.worktree_dir,
                    "branch": self.branch_name,
                    "base_ref": ref
                }
            else:
                # Stale directory - discard first
                self.discard_worktree(delete_branch=False)

        # Ensure parent directory exists
        parent_dir = os.path.dirname(self.worktree_dir)
        os.makedirs(parent_dir, exist_ok=True)

        # Check if target branch already exists
        branch_check = self._run_git(["rev-parse", "--verify", f"refs/heads/{self.branch_name}"])
        if branch_check.returncode == 0:
            cmd = ["worktree", "add", self.worktree_dir, self.branch_name]
        else:
            cmd = ["worktree", "add", "-b", self.branch_name, self.worktree_dir, ref]

        res = self._run_git(cmd)
        if res.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to create worktree: {res.stderr.strip() or res.stdout.strip()}"
            }

        return {
            "success": True,
            "reused": False,
            "worktree_path": self.worktree_dir,
            "branch": self.branch_name,
            "base_ref": ref
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns the status of the isolated worktree."""
        if not self.is_git_repo():
            return {"is_git": False, "is_worktree_active": False}

        is_active = os.path.exists(self.worktree_dir)
        if not is_active:
            return {
                "is_git": True,
                "is_worktree_active": False,
                "worktree_path": "",
                "branch": self.branch_name
            }

        # Status inside worktree
        status_res = self._run_git(["status", "--porcelain"], cwd=self.worktree_dir)
        uncommitted_files = [line.strip() for line in status_res.stdout.splitlines() if line.strip()]

        # Commits ahead of base
        count_res = self._run_git(["rev-list", "--count", f"{self.base_ref}..HEAD"], cwd=self.worktree_dir)
        commits_ahead = int(count_res.stdout.strip()) if count_res.returncode == 0 and count_res.stdout.strip().isdigit() else 0

        # Shortstat
        stat_res = self._run_git(["diff", "--shortstat", self.base_ref, "HEAD"], cwd=self.worktree_dir)
        shortstat = stat_res.stdout.strip()

        return {
            "is_git": True,
            "is_worktree_active": True,
            "worktree_path": self.worktree_dir,
            "branch": self.branch_name,
            "base_ref": self.base_ref,
            "has_uncommitted_changes": len(uncommitted_files) > 0,
            "uncommitted_files": uncommitted_files,
            "commits_ahead": commits_ahead,
            "shortstat": shortstat
        }

    def get_diff(self) -> Dict[str, Any]:
        """Returns unified diff between the worktree branch (including working changes) and the base ref."""
        if not os.path.exists(self.worktree_dir):
            return {"success": False, "error": "Worktree does not exist on disk."}

        # 1. Committed diff between base and worktree HEAD
        diff_committed = self._run_git(["diff", f"{self.base_ref}...HEAD"], cwd=self.worktree_dir).stdout

        # 2. Uncommitted tracked diff in worktree
        diff_uncommitted = self._run_git(["diff", "HEAD"], cwd=self.worktree_dir).stdout

        # 3. Untracked files diff
        untracked_diffs = []
        status_res = self._run_git(["status", "--porcelain"], cwd=self.worktree_dir)
        for line in status_res.stdout.splitlines():
            if line.startswith("?? "):
                rel_file = line[3:].strip()
                # Run git diff --no-index /dev/null <rel_file>
                nd = self._run_git(["diff", "--no-index", "/dev/null", rel_file], cwd=self.worktree_dir)
                if nd.stdout:
                    untracked_diffs.append(nd.stdout)

        # 4. Summary stats
        stat_output = self._run_git(["diff", "--stat", self.base_ref], cwd=self.worktree_dir).stdout.strip()

        all_parts = [diff_committed.strip(), diff_uncommitted.strip()] + [d.strip() for d in untracked_diffs]
        full_diff = "\n\n".join([p for p in all_parts if p]).strip()

        return {
            "success": True,
            "branch": self.branch_name,
            "base_ref": self.base_ref,
            "stat": stat_output,
            "diff": full_diff
        }

    def merge_worktree(
        self,
        strategy: str = "squash",
        commit_message: Optional[str] = None,
        target_branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Safely merges the worktree changes into the target branch of the main repository,
        then cleans up the worktree.
        """
        if not os.path.exists(self.worktree_dir):
            return {"success": False, "error": "Worktree directory does not exist."}

        # Check if main repository checkout is clean (excluding .gitignore auto-configured by Circle)
        main_status = self._run_git(["status", "--porcelain"])
        dirty_lines = [
            line.strip() for line in main_status.stdout.splitlines()
            if line.strip() and not line.strip().endswith(".gitignore")
        ]
        if dirty_lines:
            return {
                "success": False,
                "error": "Main repository has uncommitted changes. Please commit or stash them before merging the worktree."
            }

        # If .gitignore was modified/created by Circle, commit it cleanly first
        gi_lines = [l.strip() for l in main_status.stdout.splitlines() if l.strip().endswith(".gitignore")]
        if gi_lines:
            self._run_git(["add", ".gitignore"])
            self._run_git(["commit", "-m", "chore: ignore .circle/ directory"])

        # Commit any uncommitted changes inside the worktree
        wt_status = self._run_git(["status", "--porcelain"], cwd=self.worktree_dir)
        if wt_status.stdout.strip():
            self._run_git(["add", "-A"], cwd=self.worktree_dir)
            auto_msg = commit_message or f"Changes from Circle Harness session {self.short_id}"
            commit_res = self._run_git(["commit", "-m", auto_msg], cwd=self.worktree_dir)
            if commit_res.returncode != 0 and "nothing to commit" not in commit_res.stdout:
                return {
                    "success": False,
                    "error": f"Failed to commit worktree changes: {commit_res.stderr.strip()}"
                }

        # Determine target branch in main repo
        current_branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        target = target_branch or current_branch or "main"

        # If on another branch, switch to target
        if current_branch != target:
            checkout_res = self._run_git(["checkout", target])
            if checkout_res.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to checkout target branch '{target}': {checkout_res.stderr.strip()}"
                }

        msg = commit_message or f"Merge isolated worktree changes ({self.branch_name})"

        if strategy == "squash":
            merge_res = self._run_git(["merge", "--squash", self.branch_name])
            if merge_res.returncode != 0:
                self._run_git(["merge", "--abort"])
                return {
                    "success": False,
                    "error": f"Squash merge failed with conflicts: {merge_res.stderr.strip() or merge_res.stdout.strip()}"
                }
            # Commit the squashed changes
            commit_res = self._run_git(["commit", "-m", msg])
            if commit_res.returncode != 0 and "nothing to commit" not in commit_res.stdout:
                return {
                    "success": False,
                    "error": f"Failed to commit squashed merge: {commit_res.stderr.strip()}"
                }
        elif strategy == "ff":
            merge_res = self._run_git(["merge", "--ff-only", self.branch_name])
            if merge_res.returncode != 0:
                return {
                    "success": False,
                    "error": f"Fast-forward merge not possible: {merge_res.stderr.strip()}"
                }
        else:  # standard merge
            merge_res = self._run_git(["merge", "--no-ff", "-m", msg, self.branch_name])
            if merge_res.returncode != 0:
                self._run_git(["merge", "--abort"])
                return {
                    "success": False,
                    "error": f"Merge failed with conflicts: {merge_res.stderr.strip()}"
                }

        # Cleanup worktree and branch
        self.discard_worktree(delete_branch=True)

        return {
            "success": True,
            "message": f"Successfully merged worktree changes into '{target}'.",
            "target_branch": target
        }

    def discard_worktree(self, delete_branch: bool = True) -> Dict[str, Any]:
        """
        Removes the worktree directory and administrative reference.
        Optionally deletes the temporary worktree branch.
        """
        # 1. Git worktree remove
        self._run_git(["worktree", "remove", "--force", self.worktree_dir])
        self._run_git(["worktree", "prune"])

        # 2. Filesystem cleanup if directory remnants remain
        if os.path.exists(self.worktree_dir):
            safe_rmtree(self.worktree_dir)

        # 3. Delete worktree branch if requested
        if delete_branch:
            self._run_git(["branch", "-D", self.branch_name])

        return {
            "success": True,
            "message": f"Worktree '{self.worktree_dir}' and branch '{self.branch_name}' discarded."
        }
