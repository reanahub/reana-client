Changes
=======

Version 0.8.0 (UNRELEASED)
--------------------------

- Adds new command ``quota-show``.
- Adds possibility to filter by workflow status and search by workflow name to ``list`` command.
- Adds job start and finish times to ``logs`` command output.
- Adds possibility to filter by file name, size and last modified values to ``ls`` command.
- Adds new command ``info`` that retrieves general information about the cluster.
- Adds new ``--server-capabilities`` flag to ``validate`` command.
- Adds the possibility to filter and display all the runs of a given workflow to the ``list`` command.
- Changes ``delete`` to prevent workflow hard deletion.
- Changes ``list`` to display interactive session status.
- Changes ``list`` command to stop including workflow progress and workspace size by default. Adds
  ``--include-progress`` and ``--include-workspace-size`` options to add them to the output.
- Changes Yadage workflow specification loading to be done in ``reana-commons``.
- Removes support for Python 2.

Version 0.7.6 (UNRELEASED)
--------------------------
- Adds support for ``outputs.directories`` in ``reana.yaml``

Version 0.7.5 (2021-07-05)
--------------------------

- Changes workflow validation to display more granular output.
- Changes workflow parameters validation to warn about misused parameters for each step.
- Changes dependencies to unpin six so that client may be installed in more contexts.
- Fixes environment image validation not to test repetitively the same image.
- Fixes ``upload_to_server()`` Python API function to silently skip uploading in case of none-like inputs.

Version 0.7.4 (2021-04-28)
--------------------------

- Adds support of wildcard patterns to ``ls`` command.
- Adds support of directory download and wildcard patterns to ``download`` command.
- Changes ``list`` command to include deleted workflows by default.
- Fixes environment image validation info message where UIDs were switched.

Version 0.7.3 (2021-03-24)
--------------------------

- Adds validation of workflow input parameters to the ``validate`` command.
- Adds optional validation of workflow environment images (``--environments``) to the ``validate`` command.

Version 0.7.2 (2021-01-15)
--------------------------

- Adds support for Python 3.9.
- Fixes exception handling when uploading files.
- Fixes minor code warnings.
- Fixes traling slash issue from user exported REANA_SERVER_URL.

Version 0.7.1 (2020-11-10)
--------------------------

- Changes ``ping`` command output to include REANA client and server version information.
- Fixes ``upload`` command to properly display errors.

Version 0.7.0 (2020-10-20)
--------------------------

- Adds option to ``logs`` command to filter job logs according to compute backend, docker image, status and step name.
- Adds new ``restart`` command to restart previously run or failed workflows.
- Adds possibility to specify operational options in the ``reana.yaml`` of the workflow.
- Fixes user experience by preventing dots as part of the workflow name to avoid confusion with restart runs.
- Changes ``du`` command output format.
- Changes file loading to optimise CLI performance.
- Changes ``logs`` command to enhance formatting using marks and colours.
- Changes from Bravado to requests to improve download performance.
- Changes ``ping`` command to perform user access token validation.
- Changes defaults to accept both ``reana.yaml`` and ``reana.yml`` filenames.
- Changes ``diff`` command to improve output formatting.
- Changes code formatting to respect ``black`` coding style.
- Changes documentation to single-page layout.

Version 0.6.1 (2020-06-09)
--------------------------

- Fixes installation troubles for REANA 0.6.x release series by pinning several
  dependencies.

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
