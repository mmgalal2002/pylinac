.. _exporting-results:

=================
Exporting Results
=================

After analyzing a dataset in pylinac, you may want to export the data to a file for further analysis or for record-keeping.
Pylinac has built-in methods for **most** analyses to export to PDF, save figures, and dump data to string or JSON.


Exporting to PDF
----------------

For most analyses, the ``publish_pdf`` method is available. This method will create a PDF report of the analysis. The PDF will contain a summary of the analysis, the figure(s) generated, and any other relevant information.

.. code-block:: python

    from pylinac import WinstonLutz

    wl = WinstonLutz.from_zip("myzip.zip")
    wl.analyze()
    wl.publish_pdf("my_report.pdf")  # will save the report to a PDF file

You can even open this upon saving by setting the ``open_file`` parameter to ``True``.

.. code-block:: python

    ...
    wl.publish_pdf(
        "my_report.pdf", open_file=True
    )  # will save the report to a PDF file and open it

Detailed Imaging Reports
------------------------

X-ray imaging, CT, MRI and mammography analyses support opt-in detailed reports.
Existing calls keep the legacy layout. Request the complete report explicitly:

.. code-block:: python

    wl.publish_pdf("winston_lutz_detailed.pdf", detailed=True)

The detailed PDF includes all recorded structured measurements, paginated tables,
analysis warnings and separate analysis artifacts. The exact results snapshot is
also attached as JSON, with its original numeric precision. Display rounding does
not change measurements or tolerance decisions. Winston-Lutz reports include
each image separately; mammography reports retain individual mass, speck-group
and fibre detail views.

Use a ``branding`` mapping to change the full report identity:

.. code-block:: python

    wl.publish_pdf(
        "winston_lutz_branded.pdf",
        detailed=True,
        metadata={"Unit": "Treatment unit", "Reviewer": "Medical physicist"},
        notes="For local review",
        branding={
            "name": "Clinic QA",
            "report_title": "Winston-Lutz Review",
            "primary_color": "#165A70",
            "chart_color": "#287A63",
            "header_text": "Medical physics quality assurance",
            "footer_text": "Local review copy",
        },
    )

See :class:`~pylinac.core.reporting.ReportBranding` for fonts, colours, headers,
footers and other supported settings. Custom fonts must already be registered
with ReportLab. No extra PDF dependency or external service is required.
File paths and caller-owned binary streams are supported; streams remain open.
``open_file=True`` applies only to file destinations in the detailed path.

Single-image :class:`~pylinac.winston_lutz.WinstonLutz2D`,
:class:`~pylinac.dlg.DLG` and
:class:`~pylinac.contrib.orthogonality.JawOrthogonality` previously had no PDF
method. Their new ``publish_pdf`` method defaults to the detailed report;
``detailed=False`` raises an explicit error because no legacy report exists.
For analyses that already had a PDF method, ``detailed=False`` remains the default.
Nuclear medicine, machine logs, calibration and non-image field devices are
outside this imaging-report rollout.

Generating Local Review Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The repository includes a local-only generator. It uses matching input files and
never downloads demo data. It writes standard and branded PDF pairs, plus
Markdown and JSON progress for every supported analysis and explicit exclusions:

.. code-block:: powershell

    uv run --no-sync python scripts/generate_detailed_report_examples.py --source "E:\dcms-20261013T142612Z-1-001\dcms" --output "E:\dcms-20261013T142612Z-1-001\detailed-reports"

Use ``--only`` followed by analysis class names to regenerate a subset.
Cases without a matching image or required clinical settings remain awaiting
input. Detection or generation failures are recorded with their stage and error;
they are not replaced with a legacy or incomplete report.

A ``--manifest`` JSON file can identify additional local inputs and settings.
Each entry is keyed by the analysis class name and accepts ``inputs``, ``method``,
``init``, ``analyze`` and ``publish`` mappings. Supported methods are local
constructors, ``from_zip`` and ``from_multiple_images``. For example:

.. code-block:: json

    {
        "ACRMRIMedium": {
            "inputs": ["approved_medium_mri.zip"],
            "method": "from_zip",
            "init": {},
            "analyze": {},
            "publish": {"notes": "Human review pending"}
        }
    }

Only use images and settings appropriate to the specified analysis. A TIFF
Starshot image without an SID tag needs its measured source-to-image distance
in the ``init`` mapping. DLG needs the actual planned overlaps and the MLC enum
name in its ``analyze`` mapping. Do not substitute assumed clinical measurements.
Generation alone is not clinical acceptance: review the field labels, units,
warnings, all artifacts and the results snapshot before using a report.

Exporting Figures
-----------------

If you want to save the figures generated during an analysis, you can use the ``save_analyzed_image`` method. This method will save the figure to a file.

.. code-block:: python

    from pylinac import Starshot

    star = Starshot.from_zip("myzip.zip")
    star.analyze()
    star.save_analyzed_image("my_starshot.png")  # will save the figure to a PNG file

Exporting to JSON
-----------------

If you want to save the data to a JSON file, you can use the ``results_data(to_json=True)`` method. This method will return a JSON string of the data.
This string can be saved to a file or otherwise passed around.

.. code-block:: python

    from pylinac import Starshot

    star = Starshot.from_zip("myzip.zip")
    star.analyze()
    json_str = star.results_data(
        to_json=True
    )  # dumps to a string that can be loaded by any JSON reader
    with open("my_starshot.json", "w") as f:
        f.write(json_str)

.. _exporting-to-quaac:

Exporting to QuAAC
------------------

.. note::

   `QuAAC <https://quaac.readthedocs.io/en/latest/index.html>`__ is a new standard we designed to allow for interoperable data exchange between vendors and clinics.
   It is in the early stages of development and is not yet widely adopted.

To save results from an analysis to the QuAAC format, use the ``to_quaac()`` method. This will save the
data to a file in the QuAAC format.

.. code-block:: python

    from pylinac import Starshot
    from quaac import User, Equipment

    star = Starshot.from_zip("myzip.zip")
    star.analyze()
    performer = User(name="Michael Bluth", email="mbluth@sitwell.com")
    equipment = Equipment(
        name="Halcyon 1",
        type="Linac",
        serial_number="1234",
        manufacturer="Varian",
        model="Halcyon",
    )
    star.to_quaac(
        "star_quaac.yaml", format="yaml", performer=performer, primary_equipment=equipment
    )

It is important to know that QuAAC can store binary data like plotted images and PDFs that pylinac might produce.
This is not done by default due to the many options of publishing the PDF and plotting the images.
However, this can be done by separately saving the images and PDFs and then adding them to the QuAAC file
as attachments.

.. code-block:: python

    from pylinac import Starshot
    from quaac import User, Equipment, Attachment

    star = Starshot.from_zip("myzip.zip")
    star.analyze()
    # save the images and PDFs
    star.save_analyzed_image("starshot.png")
    star.publish_pdf("starshot_report.pdf")
    # now dump to QuAAC
    performer = User(name="Michael Bluth", email="mbluth@sitwell.com")
    equipment = Equipment(
        name="Halcyon 1",
        type="Linac",
        serial_number="1234",
        manufacturer="Varian",
        model="Halcyon",
    )
    png_attachment = Attachment.from_file(path="starshot.png", name="Starshot Image")
    pdf_attachment = Attachment.from_file(
        path="starshot_report.pdf", name="Starshot Report"
    )
    original_image = Attachment.from_file(path="myzip.zip", name="Raw Image")
    star.to_quaac(
        "star_quaac.yaml",
        format="yaml",
        performer=performer,
        primary_equipment=equipment,
        attachments=[png_attachment, pdf_attachment, original_image],
    )

See more `here <https://quaac.readthedocs.io/en/latest/writing_quaac.html#writing-quaac-files>`__ for writing QuAAC files.
