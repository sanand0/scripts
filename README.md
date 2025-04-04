# Scripts

These are personal productivity utilities that simplify my workflow.

I clone this into `~/code/scripts/` and configure my shell to source the scripts from there.

This is intended to work with fish and bash on both Ubuntu and Cygwin.

## Setup

```bash
# Configure fish, which is my default shell
echo 'source ~/code/scripts/setup.fish' >> ~/.config/fish/config.fish

# Configure bash, which was my earlier default
echo 'source ~/code/scripts/setup.bash' >> ~/.bashrc

# Configure git shortcuts
ln -s ~/code/scripts/.gitconfig ~/.gitconfig
```
