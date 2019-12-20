Changes
=======

Version 0.6.0 (2019-12-27)
--------------------------

- Introduces user secrets management commands ``secrets-add``,
  ``secrets-list`` and ``secrets-delete``.
- Enhances ``run`` and ``create`` commands to allow specifying
  workfow via the ``--workflow`` flag.
- Introduces new command ``version`` to report client version.
- Fixes ``upload`` command behaviour for uploading very large files.
- Simplifies ``run`` command by removing free upload parameters.
- Upgrades ``cwltool`` to 1.0.20191022103248.
- Disables SSL verification warnings when talking to self-signed server
  certificates.

Version 0.5.0 (2019-04-24)
--------------------------

- Introduces new ``resources`` field in ``reana.yaml`` specification file
  allowing to declare computing resources needed for workflow runs, such as the
  CVMFS repositories via ``cvmfs`` subfield.
- Improves ``reana-client`` embedded command-line documentation (``-help``) by
  grouping commands and providing concrete usage examples for all commands.
- Enhances workflow ``start`` command allowing to override input parameters
  (``--parameter``) and to specify additional operational options
  (``--option``).
- Introduces new workflow ``run`` wrapper command that creates workflow, uploads
  its input data and code and starts its execution.
- Introduces new workflow ``stop`` command for stopping a running workflow.
- Enhances workflow ``logs`` command output capabilities via new ``--json``
  option.
- Introduces new workflow ``diff`` command for comparing two workflow runs.
- Introduces new workflow ``delete`` command for deleting one or more workflow
  runs.
- Introduces new session ``open`` command allowing to run interactive sessions
  such as Jupyter notebook upon workflow workspace.
- Introduces new session ``close`` command for closing interactive sessions.
- Renames past ``workflows`` command to ``list`` allowing to list both workflow
  runs and interactive sessions.
- Introduces new workspace ``du`` command for checking workspace disk usage.
- Introduces new workspace ``mv`` command for moving files within workspace.
- Introduces new workspace ``rm`` command for removing files within workspace.
- Renames past workspace ``list`` command to ``ls`` allowing to list workspace
  files. Enhances its output capabilities via new ``--format`` option.
- Introduces new API function ``create_workflow_from_json()`` which allows
  developers and third-party systems to create workflows directly from JSON
  specification.

Version 0.4.0 (2018-11-07)
--------------------------

- Enhances test suite and increases code coverage.
- Changes license to MIT.

Version 0.3.1 (2018-09-25)
--------------------------

- Amends upload and download commands that will now upload/download all the
  files specified in ``reana.yaml`` in case no arguments are provided.
- Fixes ``status`` command's JSON output mode.
- Upgrades CWL reference implementation to version ``1.0.20180912090223``.
- Renames Serial workflow operational parameter from ``CACHING``to ``CACHE``.
- Adds support for Python 3.7.

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
