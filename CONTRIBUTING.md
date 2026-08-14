# Contributing to tanzu-validated-solutions

The tanzu-validated-solutions project team welcomes contributions from the
community. Before you start working with tanzu-validated-solutions, please read
our [Developer Certificate of Origin](https://cla.vmware.com/dco). All
contributions to this repository must be signed as described on that page using
the `Signed-Off-By` commit header. Your signature certifies that you wrote the
patch or have the right to pass it on as an open-source patch.

Use `git commit --signoff` to sign your commits. We recommend adding an alias
to your Git configuration file at `$HOME/.gitconfig` to make this easier. To
create an alias (like `git cs` instead of `git commit --signoff`), add this
block of code to your `$HOME/.gitconfig` file:

```gitconfig
[alias]
  cs = commit --signoff
```

> ✅ GitHub will not allow you to sign off commits with a personal email
> if you have chosen to [keep your commits
> private](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-github-user-account/managing-email-preferences/setting-your-commit-email-address).
> To work-around this without disabling this feature, add a working email address
> that you are okay to use for signing off to commit but
> **do not add it to your profile.**
>
> If you wish to sign off com

## Contribution Flow

This is a rough outline of what a contributor's workflow looks like:

- Create a topic branch from where you want to base your work
- Make commits of logical units
- Make sure your commit messages are in the proper format (see below)
- Test locally
- Push your changes to a topic branch in your fork of the repository
- Submit a pull request

Example:

``` shell
git remote add upstream https://github.com/vmware/@(project).git
git checkout -b my-new-feature main
git commit -a
docker compose run --rm tests
git push origin my-new-feature
```

### Staying In Sync With Upstream

When your branch gets out of sync with the vmware/main branch, use the following to update:

``` shell
git checkout my-new-feature
git fetch -a
git pull --rebase upstream main
git push --force-with-lease origin my-new-feature
```

### Updating pull requests

If your PR fails to pass CI or needs changes based on code review, you'll most likely want to squash these changes into
existing commits.

If your pull request contains a single commit or your changes are related to the most recent commit, you can simply
amend the commit.

``` shell
git add .
git commit --amend
git push --force-with-lease origin my-new-feature
```

If you need to squash changes into an earlier commit, you can use:

``` shell
git add .
git commit --fixup <commit>
git rebase -i --autosquash upstream/main
git push --force-with-lease origin my-new-feature
```

Be sure to add a comment to the PR indicating your new changes are ready to review, as GitHub does not generate a
notification when you git push.

### Code Style

### Formatting Commit Messages

We follow the conventions on [How to Write a Git Commit Message](http://chris.beams.io/posts/git-commit/).

Be sure to include any related GitHub issue references in the commit message.  See
[GFM syntax](https://guides.github.com/features/mastering-markdown/#GitHub-flavored-markdown) for referencing issues
and commits.

## Reporting Bugs and Creating Issues

When opening a new issue, try to roughly follow the commit message format conventions above.
