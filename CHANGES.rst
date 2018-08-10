Changes
=======

Version 0.3.0 (2018-08-10)
--------------------------

- Adds support for
  `Serial workflows <http://reana-workflow-engine-serial.readthedocs.io/en/latest/>`_.
- CLI refactored to a flat design:
    - ``inputs``/``outputs``/``code`` removed, everything is a file managed
      with upload/download/list commands.
    - Removes ``workflow`` command, workflows are managed with
      ``create``/``start``/``status``.
- Removes ``analyes`` command, now ``validate`` is first level command.
- ``status`` now shows the selected workflow progress and current command on
  verbose mode.
- Requires the usage of an access token to talk to REANA Server.
- Fixes bug when uploading binary files.
- Supports addition of workflow engine parameters when using ``start`` for
  serial workflows.
- Improves error messages.


Version 0.2.0 (2018-04-20)
--------------------------

- Adds support for Common Workflow Language workflows.
- Adds support for persistent user-selected workflow names.
- Enables file and directory input uploading using absolute paths.
- Adds new ``status`` command to display the current status of the client.
- Reduces verbosity level for commands and improves error messages.

Version 0.1.0 (2018-01-30)
--------------------------

- Initial public release.

.. admonition:: Please beware

   Please note that REANA is in an early alpha stage of its development. The
   developer preview releases are meant for early adopters and testers. Please
   don't rely on released versions for any production purposes yet.
