fg_exheres: collection of [exheres scripts](http://exherbo.org/docs/exheres-for-smarties.html) for building/installing software on [Exherbo Linux](http://exherbo.org/)
--------------------

Collection of exheres for stuff which is relevant to me, but is missing in main
repos.  It's not listed in ::unavailable*, since I can't seem to follow
packaging guidelines and standards close enough.

Some exheres here shadow ones in the other repos, mostly because I prefer to use
scm versions and upstream policy is that they're too much of a burden to
maintain.
Otherwise, when I need something bumped or fixed, I usually create exheres here
first, then push the patch to the original repo, so I'll be able to use it
regardless of whether it's accepted. Downside is that old and conflicting stuff
can accumulate that way.

I use some script in the repo root for automatic validation (I tend to miss
things otherwise), check out .git* files which enable it (.gitconfig should be
in .git/config).