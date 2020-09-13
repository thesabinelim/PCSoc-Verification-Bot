"""Test the iam.verify module."""

import pytest
from time import time
from unittest.mock import patch, AsyncMock, MagicMock
from iam.verify import (
    State, proc_begin, proc_restart, state_await_name, state_await_unsw,
    state_await_zid, state_await_email, proc_send_email, state_await_code,
    proc_resend_email, state_await_id, proc_forward_id_admins,
    proc_exec_approve, proc_exec_reject, proc_resend_id, proc_display_pending,
    proc_verify_manual, proc_grant_rank
)
from iam.db import (
    MemberKey, MemberNotFound, make_def_member_data, MAX_VER_EMAILS
)
from iam.mail import MailError
from iam.config import PREFIX, VER_ROLE
import discord

VALID_NAMES = ["Sabine Lim", "Test User", "kek", "", "X Æ A-12"]
VALID_ZIDS = ["z5555555", "z1234567", "z0000000", "z5242579"]
INVALID_ZIDS = ["5555555", "z12345678", "z0", "5242579z"]
VALID_EMAILS = [
    "thesabinelim@gmail.com", "arcdelegate@unswpcsoc.com",
    "sabine.lim@unsw.edu.au", "z5242579@student.unsw.edu.au", "g@g.gg"
]
INVALID_EMAILS = ["a@a", "google.com", "email", "", "@gmail.com", "hi@"]
SAMPLE_CODES = ["cf137a", "000000", "hello_world"]

def filter_dict(dict, except_keys):
    return {k:v for k,v in dict.items() if k not in except_keys}

def new_mock_user(id):
    user = AsyncMock()
    user.id = id
    user.mention = f"@User_{user.id}#0000"
    user.typing = MagicMock()
    return user

def new_mock_channel(id):
    channel = AsyncMock()
    channel.id = id
    return channel

def new_mock_message(id):
    message = AsyncMock()
    message.id = id
    return message

def new_mock_attachment(id):
    attachment = AsyncMock()
    attachment.to_file.return_value = id
    return attachment

@pytest.mark.asyncio
async def test_proc_begin_standard():
    """User not undergoing verification can begin verification."""
    # Setup
    db = MagicMock()
    member = new_mock_user(0)
    db.get_member_data = MagicMock(side_effect=MemberNotFound(member.id, ""))
    before_time = time()

    # Call
    await proc_begin(db, None, None, member)

    # Ensure user entry in DB initialised with default data.
    db.set_member_data.assert_called_once()
    call_args = db.set_member_data.call_args.args
    assert call_args[0] == member.id
    assert filter_dict(call_args[1], [MemberKey.VER_TIME]) == \
        filter_dict(make_def_member_data(), [MemberKey.VER_TIME])
    assert call_args[1][MemberKey.VER_TIME] >= before_time and \
        call_args[1][MemberKey.VER_TIME] <= time()

    # Ensure user was sent prompt.
    member.send.assert_awaited_once_with("What is your full name as it "
        "appears on your government-issued ID?\nYou can restart this "
        f"verification process at any time by typing `{PREFIX}restart`.")

    # Ensure user state updated to awaiting name.
    db.update_member_data.assert_called_once_with(member.id,
        {MemberKey.VER_STATE: State.AWAIT_NAME})

    # Ensure no side effects occurred.
    member.add_roles.assert_not_awaited()

@pytest.mark.asyncio
async def test_proc_begin_already_verifying():
    """User already undergoing verification sent error."""
    for state in State:
        # Setup
        db = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()
        member_data[MemberKey.VER_STATE] = state
        db.get_member_data.return_value = member_data

        # Call
        await proc_begin(db, None, None, member)

        # Ensure correct user queried.
        db.get_member_data.assert_called_once_with(member.id)

        # Ensure user was sent error.
        member.send.assert_awaited_once_with("You are already undergoing the "
            f"verification process. To restart, type `{PREFIX}restart`.")

        # Ensure no side effects occurred.
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()
        db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_begin_already_verified():
    """User previously verified granted rank immediately."""
    for state in State:
        # Setup
        db = MagicMock()
        member = new_mock_user(0)
        ver_role = AsyncMock()
        admin_channel = new_mock_channel(1)
        member_data = make_def_member_data()
        member_data[MemberKey.ID_VER] = True
        member_data[MemberKey.VER_STATE] = state
        db.get_member_data.return_value = member_data

        # Call
        await proc_begin(db, ver_role, admin_channel, member)

        # Ensure correct user queried.
        db.get_member_data.assert_called_once_with(member.id)

        # Ensure user was granted rank.
        member.add_roles.assert_awaited_once_with(ver_role)

        # Ensure user was sent confirmation.
        member.send.assert_awaited_once_with("Our records show you were "
            "verified in the past. You have been granted the rank once again. "
            "Welcome back to the server!")

        # Ensure admin channel was sent confirmation.
        admin_channel.send.assert_awaited_once_with(f"{member.mention} was "
            "previously verified, and has been given the verified rank again "
            "through request.")

        # Ensure no side effects occurred.
        db.set_member_data.assert_not_called()
        db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_restart_standard():
    """User undergoing verification can restart verification."""
    for state in State:
        # Setup
        db = MagicMock()
        user = new_mock_user(0)
        member_data = make_def_member_data()
        member_data[MemberKey.VER_STATE] = state
        db.get_member_data.return_value = member_data
        before_time = time()

        # Call
        await proc_restart(db, user)

        # Ensure correct user queried.
        db.get_member_data.assert_called_once_with(user.id)

        # Ensure user entry in database updated correctly.
        call_args_list = db.update_member_data.call_args_list
        assert len(call_args_list) == 2
        call_args = call_args_list[0].args
        assert call_args[0] == user.id
        assert filter_dict(call_args[1], [MemberKey.VER_TIME]) == \
            {MemberKey.VER_STATE: None}
        assert call_args[1][MemberKey.VER_TIME] >= before_time and \
            call_args[1][MemberKey.VER_TIME] < time()

        # Ensure user was sent prompt.
        user.send.assert_awaited_once_with("What is your full name as it "
            "appears on your government-issued ID?\nYou can restart this "
            f"verification process at any time by typing `{PREFIX}restart`.")

        # Ensure user state updated to awaiting name.
        db.update_member_data.assert_called_with(user.id,
            {MemberKey.VER_STATE: State.AWAIT_NAME})

        # Ensure no side effects occurred.
        user.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_restart_never_verifying():
    """User never started verification sent error."""
    # Setup
    db = MagicMock()
    user = new_mock_user(0)
    db.get_member_data = MagicMock(side_effect=MemberNotFound(user.id, ""))

    # Call
    await proc_restart(db, user)

    # Ensure correct user queried.
    db.get_member_data.assert_called_once_with(user.id)

    # Ensure user was sent error.
    user.send.assert_awaited_once_with("You are not currently being verified.")

    # Ensure no side effects occurred.
    user.add_roles.assert_not_awaited()
    db.set_member_data.assert_not_called()
    db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_restart_not_verifying():
    """User not undergoing verification sent error."""
    # Setup
    db = MagicMock()
    user = new_mock_user(0)
    db.get_member_data.return_value = make_def_member_data()

    # Call
    await proc_restart(db, user)

    # Ensure correct user queried.
    db.get_member_data.assert_called_once_with(user.id)

    # Ensure user was sent error.
    user.send.assert_awaited_once_with("You are not currently being verified.")

    # Ensure no side effects occurred.
    user.add_roles.assert_not_awaited()
    db.set_member_data.assert_not_called()
    db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_restart_already_verified():
    """User already verified sent error."""
    for state in State:
        # Setup
        db = MagicMock()
        user = new_mock_user(0)
        member_data = make_def_member_data()
        member_data[MemberKey.ID_VER] = True
        member_data[MemberKey.VER_STATE] = state
        db.get_member_data.return_value = member_data

        # Call
        await proc_restart(db, user)

        # Ensure correct user queried.
        db.get_member_data.assert_called_once_with(user.id)

        # Ensure user was sent error.
        user.send.assert_awaited_once_with("You are already verified.")

        # Ensure no side effects occurred.
        user.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()
        db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_name_standard():
    """User sending valid name moves on to UNSW student question."""
    # Setup
    db = MagicMock()
    member = new_mock_user(0)
    full_name = "Test User 0"

    # Call
    await state_await_name(db, member, full_name)

    # Ensure user entry in database updated correctly.
    call_args_list = db.update_member_data.call_args_list
    assert len(call_args_list) == 2
    call_args = call_args_list[0].args
    assert call_args == (member.id, {MemberKey.NAME: full_name})

    # Ensure user was sent prompt.
    member.send.assert_awaited_once_with("Are you a UNSW student? Please type "
        "`y` or `n`.")

    # Ensure user state updated to awaiting is UNSW.
    call_args = call_args_list[1].args
    assert call_args == (member.id, {MemberKey.VER_STATE: State.AWAIT_UNSW})

    # Ensure no side effects occurred.
    member.add_roles.assert_not_awaited()
    db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_name_too_long():
    """User sending name that is too long sent error."""
    # Setup
    db = MagicMock()
    member = new_mock_user(0)
    full_name = "a" * 501

    # Call
    await state_await_name(db, member, full_name)

    # Ensure user was sent error.
    member.send.assert_awaited_once_with(f"Name must be 500 characters or "
        "fewer. Please try again.")

    # Ensure no side effects occurred.
    member.add_roles.assert_not_awaited()
    db.set_member_data.assert_not_called()
    db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_unsw_yes():
    """User answering yes moves on to zID question."""
    for ans in ["y", "Y", "yes", "Yes", "YES"]:
        # Setup
        db = MagicMock()
        member = new_mock_user(0)

        # Call
        await state_await_unsw(db, member, ans)

        # Ensure user was sent prompt.
        member.send.awaited_once_with("What is your zID?")

        # Ensure user state updated to awaiting zID.
        db.update_member_data.assert_called_once_with(member.id,
            {MemberKey.VER_STATE: State.AWAIT_ZID})

        # Ensure no side effects occurred.
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_unsw_no():
    """User answering no moves on to email question."""
    for ans in ["n", "N", "no", "No", "NO"]:
        # Setup
        db = MagicMock()
        member = new_mock_user(0)

        # Call
        await state_await_unsw(db, member, ans)

        # Ensure user was sent prompt.
        member.send.awaited_once_with("What is your email address?")

        # Ensure user state updated to awaiting email.
        db.update_member_data.assert_called_once_with(member.id,
            {MemberKey.VER_STATE: State.AWAIT_EMAIL})

        # Ensure no side effects occurred.
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_unsw_unrecognised():
    """User typing unrecognised response sent error."""
    # Setup
    db = MagicMock()
    member = new_mock_user(0)
    ans = "kek"

    # Call
    await state_await_unsw(db, member, ans)

    # Ensure user was sent error.
    member.send.assert_awaited_once_with("Please type `y` or `n`.")

    # Ensure no side effects occurred.
    member.add_roles.assert_not_awaited()
    db.set_member_data.assert_not_called()
    db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_zid_standard():
    """User sending valid zID moves on to proc_send_email."""
    for zid in VALID_ZIDS:
        # Setup
        db = MagicMock()
        mail = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()
        email = f"{zid}@student.unsw.edu.au"

        # Call
        with patch("iam.verify.proc_send_email") as mock_proc_send_email:
            await state_await_zid(db, mail, member, member_data, zid)

        # Ensure user entry in database updated accordingly.
        db.update_member_data.assert_called_once_with(member.id, {
            MemberKey.ZID: zid,
            MemberKey.EMAIL: email
        })

        # Ensure proc_send_email called.
        mock_proc_send_email.assert_awaited_once_with(db, mail, member, 
            member_data, email)

        # Ensure no side effects occurred.
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_zid_invalid():
    """User sending invalid zID sent error."""
    for zid in INVALID_ZIDS:
        # Setup
        db = MagicMock()
        mail = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()
        email = f"{zid}@student.unsw.edu.au"

        # Call
        with patch("iam.verify.proc_send_email") as mock_proc_send_email:
            await state_await_zid(db, mail, member, member_data, zid)

        # Ensure user was sent error.
        member.send.assert_awaited_once_with("Your zID must match the "
            "following format: `zXXXXXXX`. Please try again")

        # Ensure no side effects occurred.
        mock_proc_send_email.assert_not_called()
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()
        db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_email_standard():
    """User sending valid email moves on to proc_send_email."""
    for email in VALID_EMAILS:
        # Setup
        db = MagicMock()
        mail = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()

        # Call
        with patch("iam.verify.proc_send_email") as mock_proc_send_email:
            await state_await_email(db, mail, member, member_data, email)

        # Ensure user entry in database updated accordingly.
        db.update_member_data.assert_called_once_with(member.id, {
            MemberKey.EMAIL: email
        })

        # Ensure proc_send_email called.
        mock_proc_send_email.assert_awaited_once_with(db, mail, member, 
            member_data, email)

        # Ensure no side effects occurred.
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_email_invalid():
    """User sending invalid email sent error."""
    for email in INVALID_EMAILS:
        # Setup
        db = MagicMock()
        mail = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()

        # Call
        with patch("iam.verify.proc_send_email") as mock_proc_send_email:
            await state_await_email(db, mail, member, member_data, email)

        # Ensure user was sent error.
        member.send.assert_awaited_once_with("That is not a valid email "
            "address. Please try again.")

        # Ensure no side effects occurred.
        mock_proc_send_email.assert_not_called()
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()
        db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_send_email_standard():
    """User sent email moves on to code question."""
    for email in VALID_EMAILS:
        # Setup
        db = MagicMock()
        mail = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()
        code = "cf137a"

        # Call
        with patch("iam.verify.get_code") as mock_get_code:
            mock_get_code.return_value = code
            await proc_send_email(db, mail, member, member_data, email)

        # Ensure user was sent email.
        mail.send_email.assert_called_once_with(email, 
            "PCSoc Discord Verification", f"Your code is {code}")

        # Ensure user entry in database updated accordingly.
        call_args_list = db.update_member_data.call_args_list
        assert len(call_args_list) == 2
        call_args = call_args_list[0].args
        assert call_args == (member.id, {
            MemberKey.EMAIL_ATTEMPTS: member_data[MemberKey.EMAIL_ATTEMPTS] + 1
        })

        # Ensure user was sent prompt.
        member.send.assert_awaited_once_with("Please enter the code sent to "
            "your email (check your spam folder if you don't see it).\n"
            f"You can request another email by typing `{PREFIX}resend`.")

        # Ensure user state updated to awaiting code.
        call_args = call_args_list[1].args
        assert call_args == (member.id, {
            MemberKey.VER_STATE: State.AWAIT_CODE
        })

        # Ensure no side effects occurred.
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_send_email_out_of_attempts():
    """User who was sent too many emails previously sent error."""
    for email in VALID_EMAILS:
        # Setup
        db = MagicMock()
        mail = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()
        member_data[MemberKey.EMAIL_ATTEMPTS] = MAX_VER_EMAILS

        # Call
        await proc_send_email(db, mail, member, member_data, email)

        # Ensure user was sent error.
        member.send.assert_awaited_once_with("You have requested too many "
            "emails. Please DM an exec to continue verification.")

        # Ensure user not sent email.
        mail.send_email.assert_not_called()

        # Ensure no side effects occurred.
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()
        db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_send_email_failed():
    """When email bounces, user sent error without using up an attempt."""
    for email in VALID_EMAILS:
        # Setup
        db = MagicMock()
        mail = MagicMock()
        mail.send_email = MagicMock(side_effect=MailError(email))
        member = new_mock_user(0)
        member_data = make_def_member_data()
        code = "cf137a"

        # Call
        with patch("iam.verify.get_code") as mock_get_code:
            mock_get_code.return_value = code
            await proc_send_email(db, mail, member, member_data, email)

        # Ensure email sending attempted.
        mail.send_email.assert_called_once_with(email, 
            "PCSoc Discord Verification", f"Your code is {code}")

        # Ensure user was sent error.
        member.send.assert_awaited_once_with("Oops! Something went wrong "
            "while attempting to send you an email. Please ensure that your "
            "details have been entered correctly.")

        # Ensure no side effects occurred.
        member.add_roles.assert_not_awaited()
        db.set_member_data.assert_not_called()
        db.update_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_code_unsw():
    """Student sending matching code verified."""
    for zid in VALID_ZIDS:
        for code in SAMPLE_CODES:
            # Setup
            db = MagicMock()
            ver_role = AsyncMock()
            member = new_mock_user(0)
            admin_channel = new_mock_channel(1)
            member_data = make_def_member_data()
            member_data[MemberKey.ZID] = zid
            before_time = time()

            # Call
            with patch("iam.verify.get_code") as mock_get_code:
                mock_get_code.return_value = code
                with patch("iam.verify.proc_grant_rank") as \
                    mock_proc_grant_rank:
                    await state_await_code(db, ver_role, admin_channel, member,
                        member_data, code)

            # Ensure user entry in DB updated correctly.
            call_args_list = db.update_member_data.call_args_list
            assert len(call_args_list) == 2
            call_args = call_args_list[0].args
            assert call_args[0] == member.id
            assert filter_dict(call_args[1], [MemberKey.VER_TIME]) == \
                {MemberKey.EMAIL_VER: True}
            assert call_args[1][MemberKey.VER_TIME] >= before_time and \
                call_args[1][MemberKey.VER_TIME] <= time()
            call_args = call_args_list[1].args
            assert call_args == (member.id, {MemberKey.ID_VER: True})

            # Ensure user granted rank.
            mock_proc_grant_rank.assert_awaited_once()

            # Ensure no side effects occurred.
            member.add_roles.assert_not_called()
            db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_code_non_unsw():
    """Non-student sending matching code moves on to ID question."""
    """Student sending matching code verified."""
    for code in SAMPLE_CODES:
        # Setup
        db = MagicMock()
        ver_role = AsyncMock()
        member = new_mock_user(0)
        admin_channel = new_mock_channel(1)
        member_data = make_def_member_data()
        before_time = time()

        # Call
        with patch("iam.verify.get_code") as mock_get_code:
            mock_get_code.return_value = code
            await state_await_code(db, ver_role, admin_channel, member,
                member_data, code)

        # Ensure user entry in DB updated correctly.
        call_args_list = db.update_member_data.call_args_list
        assert len(call_args_list) == 2
        call_args = call_args_list[0].args
        assert call_args[0] == member.id
        assert filter_dict(call_args[1], [MemberKey.VER_TIME]) == \
            {MemberKey.EMAIL_VER: True}
        assert call_args[1][MemberKey.VER_TIME] >= before_time and \
            call_args[1][MemberKey.VER_TIME] <= time()

        # Ensure user was sent prompt.
        assert member.send.awaited_once_with("Please send a message with "
            "a photo of your government-issued ID attached.")

        # Ensure user state updated to awaiting ID.
        call_args = call_args_list[1].args
        assert call_args == (member.id,
            {MemberKey.VER_STATE: State.AWAIT_ID})

        # Ensure no side effects occurred.
        member.add_roles.assert_not_called()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_code_invalid_unsw():
    """Student sending non-matching code sent error."""
    for zid in VALID_ZIDS:
        for expected_code in SAMPLE_CODES:
            for received_code in ["wowee", "", "1nv4l1d", "!"]:
                # Setup
                db = MagicMock()
                ver_role = AsyncMock()
                member = new_mock_user(0)
                admin_channel = new_mock_channel(1)
                member_data = make_def_member_data()
                member_data[MemberKey.ZID] = zid
                before_time = time()

                # Call
                with patch("iam.verify.get_code") as mock_get_code:
                    mock_get_code.return_value = expected_code
                    await state_await_code(db, ver_role, admin_channel, member,
                        member_data, received_code)

                # Ensure user was sent error.    
                member.send.assert_awaited_once_with("That was not the "
                    "correct code. Please try again.\nYou can request another "
                    f"email by typing `{PREFIX}resend`.")

                # Ensure no side effects occurred.
                member.add_roles.assert_not_called()
                db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_code_invalid_non_unsw():
    """Non-student sending non-matching code sent error."""
    for expected_code in SAMPLE_CODES:
        for received_code in ["wowee", "", "1nv4l1d", "!"]:
            # Setup
            db = MagicMock()
            ver_role = AsyncMock()
            member = new_mock_user(0)
            admin_channel = new_mock_channel(1)
            member_data = make_def_member_data()
            before_time = time()

            # Call
            with patch("iam.verify.get_code") as mock_get_code:
                mock_get_code.return_value = expected_code
                await state_await_code(db, ver_role, admin_channel, member,
                    member_data, received_code)

            # Ensure user was sent error.    
            member.send.assert_awaited_once_with("That was not the "
                "correct code. Please try again.\nYou can request another "
                f"email by typing `{PREFIX}resend`.")

            # Ensure no side effects occurred.
            member.add_roles.assert_not_called()
            db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_resend_email_standard():
    """User requesting resend sent another email."""
    for email in VALID_EMAILS:
        # Setup
        db = MagicMock()
        mail = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()
        member_data[MemberKey.EMAIL] = email
        member_data[MemberKey.VER_STATE] = State.AWAIT_CODE

        # Call
        with patch("iam.verify.proc_send_email") as mock_proc_send_email:
            await proc_resend_email(db, mail, member, member_data)

        # Ensure proc_send_email called.
        mock_proc_send_email.assert_awaited_once_with(db, mail, member,
            member_data, email)

        # Ensure no side effects occurred.
        member.add_roles.assert_not_called()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_resend_email_not_awaiting_code():
    """User not awaiting code ignored."""
    for email in VALID_EMAILS:
        for state in State:
            if state == State.AWAIT_CODE:
                pass
        # Setup
        db = MagicMock()
        mail = MagicMock()
        member = new_mock_user(0)
        member_data = make_def_member_data()
        member_data[MemberKey.EMAIL] = email
        member_data[MemberKey.VER_STATE] = state

        # Call
        with patch("iam.verify.proc_send_email") as mock_proc_send_email:
            await proc_resend_email(db, mail, member, member_data)

        # Ensure proc_send_email not called.
        mock_proc_send_email.assert_not_awaited()

        # Ensure no side effects occurred.
        member.add_roles.assert_not_called()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_id_standard():
    """User sending attachments forwarded to admin channel."""
    for n_attach in range(1, 11):
        # Setup
        db = MagicMock()
        member = new_mock_user(0)
        admin_channel = new_mock_channel(1)
        member_data = make_def_member_data()
        attachments = [new_mock_attachment(i) for i in range(n_attach)]

        # Call
        with patch("iam.verify.proc_forward_id_admins") as \
            mock_proc_forward_id_admins:
            await state_await_id(db, admin_channel, member, member_data,
                attachments)

        # Ensure proc_forward_id_admins called.
        mock_proc_forward_id_admins.assert_awaited_once_with(db, member,
            admin_channel, member_data, attachments)

        # Ensure no side effects occurred.
        member.add_roles.assert_not_called()
        db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_state_await_id_no_attachments():
    """User sending no attachments sent error."""
    # Setup
    db = MagicMock()
    member = new_mock_user(0)
    admin_channel = new_mock_channel(1)
    member_data = make_def_member_data()
    attachments = []

    # Call
    with patch("iam.verify.proc_forward_id_admins") as \
        mock_proc_forward_id_admins:
        await state_await_id(db, admin_channel, member, member_data,
            attachments)

    # Ensure proc_forward_id_admins not called.
    mock_proc_forward_id_admins.assert_not_awaited()

    # Ensure no side effects occurred.
    member.add_roles.assert_not_called()
    db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_forward_id_admins_standard():
    """Message containing attachments sent to admin channel."""
    for full_name in VALID_NAMES:
        for n_attach in range(1, 11):
            # Setup
            db = MagicMock()
            member = new_mock_user(0)
            admin_channel = new_mock_channel(1)
            admin_channel.send.return_value = new_mock_message(1337)
            member_data = make_def_member_data()
            member_data[MemberKey.NAME] = full_name
            attachments = [new_mock_attachment(i) for i in range(n_attach)]

            # Call
            await proc_forward_id_admins(db, member, admin_channel,
                member_data, attachments)

            # Ensure attachments forwarded to admin channel.
            admin_channel.send.assert_awaited_once_with("Received "
                f"attachment(s) from {member.mention}. Please verify that "
                f"name on ID is `{full_name}`, then type `{PREFIX}verify "
                f"approve {member.id}` or `{PREFIX}verify reject {member.id} "
                "\"reason\"`.", files=[await a.to_file() for a in attachments])

            # Ensure user entry in database updated accordingly.
            call_args_list = db.update_member_data.call_args_list
            assert len(call_args_list) == 2
            call_args = call_args_list[0].args
            assert call_args == (member.id, {MemberKey.ID_MESSAGE: 1337})

            # Ensure notification sent to user.
            member.send.assert_awaited_once_with("Your attachment(s) have "
                "been forwarded to the execs. Please wait.")

            # Ensure user state updated to awaiting approval.
            call_args = call_args_list[1].args
            assert call_args == (member.id,
                {MemberKey.VER_STATE: State.AWAIT_APPROVAL})

            # Ensure no side effects occurred.
            member.add_roles.assert_not_called()
            db.set_member_data.assert_not_called()

@pytest.mark.asyncio
async def test_proc_exec_approve_standard():
    """Exec approving verifying user grants rank to user."""
    pass

@pytest.mark.asyncio
async def test_proc_exec_approve_not_awaiting():
    """Exec approving user not awaiting approval sends error."""
    pass

@pytest.mark.asyncio
async def test_proc_exec_approve_not_verifying():
    """Exec approving user not verifying sends error."""
    pass

@pytest.mark.asyncio
async def test_proc_exec_approve_never_verifying():
    """Exec approving user never started verification sends error."""

@pytest.mark.asyncio
async def test_proc_exec_reject_standard():
    """Exec rejecting verifying user notifies user and updates accordingly."""
    pass

@pytest.mark.asyncio
async def test_proc_exec_reject_not_awaiting():
    """Exec rejecting user not verifying sends error."""
    pass

@pytest.mark.asyncio
async def test_proc_exec_reject_not_verifying():
    """Exec rejecting user not verifying sends error."""
    pass

@pytest.mark.asyncio
async def test_proc_exec_reject_never_verifying():
    """Exec rejecting user never started verification sends error."""

@pytest.mark.asyncio
async def test_proc_display_pending_standard():
    """Send list of pending approvals on request."""
    pass

@pytest.mark.asyncio
async def test_proc_display_pending_none():
    """Send error if no pending approvals."""
    pass

@pytest.mark.asyncio
async def test_proc_resend_id_standard():
    """Retrieve previous message attachments and resend."""
    pass

@pytest.mark.asyncio
async def test_proc_resend_id_not_awaiting():
    """Send error if user not awaiting approval."""
    pass

@pytest.mark.asyncio
async def test_proc_resend_id_not_verifying():
    """Send error if user not verifying."""
    pass

@pytest.mark.asyncio
async def test_proc_resend_id_never_verifying():
    """Send error if user never started verification."""
    pass

@pytest.mark.asyncio
async def test_proc_resend_id_not_found():
    """Send error if previous message containing attachments not found."""
    pass

@pytest.mark.asyncio
async def test_proc_verify_manual_standard():
    """Create new user entry in database and verify user."""
    pass

@pytest.mark.asyncio
async def test_proc_verify_manual_invalid_zid():
    """Send error if invalid zID entered."""
    pass

@pytest.mark.asyncio
async def test_proc_verify_manual_invalid_email():
    """Send error if invalid email entered."""
    pass

@pytest.mark.asyncio
async def test_proc_grant_rank_standard():
    """User granted rank and notified. Admin channel notified."""
    pass

async def test_proc_grant_rank_silent():
    """User granted rank. No notifications sent."""
    pass
