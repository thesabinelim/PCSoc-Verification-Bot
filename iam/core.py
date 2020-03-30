"""MIT License

Copyright (c) 2020 Computer Enthusiasts Society

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

"""Handle core functions of the bot."""

from inspect import getdoc
from discord.ext.commands import (
    Cog, Group, command, CommandNotFound, DisabledCommand, BadArgument,
    MissingRequiredArgument, TooManyArguments, ArgumentParsingError
)

from iam.log import new_logger
from iam.config import PREFIX
from iam.hooks import pre, post, log_invoke, log_success

LOG = None
"""Logger for this module."""

COG_NAME = "Core"
"""Name of this module's Cog."""

def setup(bot):
    """Add Core cog to bot and set up logging.

    Args:
        bot: Bot object to add cog to.
    """
    global LOG
    LOG = new_logger(__name__)
    LOG.debug(f"Setting up {__name__} extension...")
    cog = Core(bot, LOG)
    LOG.debug(f"Initialised {COG_NAME} cog")
    bot.add_cog(cog)
    LOG.debug(f"Added {COG_NAME} cog to bot")

def teardown(bot):
    """Remove Core cog from bot and remove logging.

    Args:
        bot: Bot object to remove cog from.
    """
    LOG.debug(f"Tearing down {__name__} extension...")
    bot.remove_cog(COG_NAME)
    LOG.debug(f"Removed {COG_NAME} cog from bot")
    for handler in LOG.handlers:
        LOG.removeHandler(handler)

class Core(Cog, name=COG_NAME):
    """Handle core functions of the bot.

    Attributes:
        bot: Bot object that registered this cog.
    """
    def __init__(self, bot, logger):
        """Initialise cog with given bot.

        Args:
            bot: Bot object that registered this cog.
        """
        LOG.debug(f"Initialising {COG_NAME} cog...")
        self.bot = bot
        self.logger = logger
        self.bot.remove_command("help")

    @Cog.listener()
    async def on_ready(self):
        """Log message on bot startup."""
        LOG.info(f"Bot running with command prefix '{PREFIX}'")

    @Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle exceptions raised by commands.

        If exception is related to incorrect command usage, attempt to display
        help for that command.

        If exception is that command does not exist or is disabled, ignore.

        If exception is not handled here, will be raised and handled by 
        on_error in bot.py.

        Args:
            ctx: Context object associated with event/command that raised.
            error: CommandError object generated by discord.py

        Raises:
            Any exception that is not handled by the above.
        """
        if isinstance(error, CommandNotFound) \
            or isinstance(error, DisabledCommand):
            return

        if isinstance(error, MissingRequiredArgument) \
            or isinstance(error, TooManyArguments) \
            or isinstance(error, ArgumentParsingError) \
            or isinstance(error, BadArgument):
            await self.show_help_single(ctx, ctx.command.qualified_name)
            return

        if hasattr(error, "original"):
            raise error.original
        raise error

    @command(
        name="help",
        help="Display this help dialogue.",
        usage=""
    )
    @pre(log_invoke())
    @post(log_success())
    async def cmd_help(self, ctx, *query):
        """Handle help command.

        If no query is given, display list of all commands, their usage,
        aliases and subcommands.

        If query is given, only display help for that command.

        Does not display help for commands with hidden attribute set to False.

        Args:
            ctx: Context object associated with command invocation.
            query: String representing name of command to display help for.
                   Optional.
        """
        if len(query) == 0:
            await self.show_help_all(ctx)
        else:
            await self.show_help_single(ctx, " ".join(query))

    async def show_help_all(self, target):
        """Send help text for all commands to target.

        Args:
            target: Object to send message to.
        """
        out = ["**All commands:**"]
        for cmd in self.bot.commands:
            if cmd.hidden:
                continue
            out.append(make_help_text(cmd))
        await target.send("\n".join(out))

    async def show_help_single(self, target, query):
        """Send help text for queried command to target.

        If no such command exists or command is hidden, send error message.

        Args:
            target: Object to send message to.
            query: String representing command to search for.
        """
        cmd = self.bot.get_command(query)
        if cmd == None or cmd.hidden:
            await target.send("No such command exists!")
            return
        await target.send(f"Usage: {make_help_text(cmd)}")

def make_help_text(cmd):
    """Generate help text for command.

    Help text will look as follows:
    **(command name) (usage)**
    (command help)
    __Aliases__ | (alias1) | (alias2) | etc.
    __Subcommands__ | (subcommand1) | (subcommand 2) etc.

    Command object should define help and usage attributes for this to work.

    Args:
        cmd: Command object to generate help text for.

    Returns:
        String representing generated help text.
    """
    help = [f"**{PREFIX}{cmd.qualified_name}** {cmd.usage}", cmd.help]

    # Append aliases.
    if len(cmd.aliases) > 0:
        aliases = ["__Aliases__"]
        aliases += [f"{PREFIX}{a}" for a in cmd.aliases]
        help.append(" | ".join(aliases))
    
    # Append subcommands.
    if isinstance(cmd, Group) \
        and len(cmd.commands) > 0:
        subs = ["__Subcommands__"]
        subs += [f"{PREFIX}{c.qualified_name}" for c in cmd.commands]
        help.append(" | ".join(subs))

    return "\n".join(help)
