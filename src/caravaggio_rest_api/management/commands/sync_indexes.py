# -*- coding: utf-8 -*
# Copyright (c) 2019 BuildGroup Data Services Inc.
# All rights reserved.
import inspect
import logging

from caravaggio_rest_api.haystack.indexes import TextField
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django_cassandra_engine.utils import get_engine_from_db_alias

try:
    from dse.cqlengine.connection import execute
    from dse.cqlengine import query
    from dse.cqlengine import columns
    from dse.cqlengine import models
except ImportError:
    from cassandra.cqlengine.connection import execute
    from cassandra.cqlengine import query
    from cassandra.cqlengine import columns
    from cassandra.cqlengine import models

from django_cassandra_engine.compat import management

from haystack.utils.loading import UnifiedIndex
from haystack import fields
from caravaggio_rest_api.haystack.indexes import TextField

_logger = logging.getLogger(__name__)


TEXT_SEARCH_JSON_SNIPPED = """
$${
    "analyzer": [
      {
        "type": "index",
        "tokenizer": { "class": "solr.StandardTokenizerFactory" },
        "filter": [
          { "class": "solr.LowerCaseFilterFactory" },
          { "class": "solr.ASCIIFoldingFilterFactory" }
        ]
      },
      {
        "type": "search",
        "tokenizer": { "class": "solr.StandardTokenizerFactory" },
        "filter": [
          { "class": "solr.LowerCaseFilterFactory" },
          { "class": "solr.ASCIIFoldingFilterFactory" }
        ]
      }
    ]
}$$
"""

STR_SEARCH_JSON_SNIPPED = """
$${
    "analyzer": [
      {
        "type": "index",
        "tokenizer": { "class": "solr.KeywordTokenizerFactory" },
        "filter": [
          { "class": "solr.LowerCaseFilterFactory" },
          { "class": "solr.ASCIIFoldingFilterFactory" }
        ]
      },
      {
        "type": "search",
        "tokenizer": { "class": "solr.KeywordTokenizerFactory" },        
        "filter": [
          { "class": "solr.LowerCaseFilterFactory" },
          { "class": "solr.ASCIIFoldingFilterFactory" }
        ]
      }
    ]
}$$
"""


def _define_types(ks_name, raw_cf_name):
    # Define a TextField type to analyze texts (tokenizer, ascii, etc.)
    try:
        execute(
            f"ALTER SEARCH INDEX SCHEMA ON {ks_name}.{raw_cf_name}"
            f" ADD types.fieldType[@name='TextField',"
            f" @class='org.apache.solr.schema.TextField']"
            f" WITH {TEXT_SEARCH_JSON_SNIPPED};"
        )
    except Exception as ex:
        _logger.warning("Maybe te field type TextField has been already" " defined in the schema. Cause: {}".format(ex))
        pass

    try:
        execute(
            f"ALTER SEARCH INDEX SCHEMA ON {ks_name}.{raw_cf_name}"
            f" ADD types.fieldType[@name='ISCStrField',"
            f" @class='org.apache.solr.schema.TextField']"
            f" WITH {STR_SEARCH_JSON_SNIPPED};"
        )
    except Exception as ex:
        _logger.warning(
            "Maybe te field type ISCStrField has been already" " defined in the schema. Cause: {}".format(ex)
        )
        pass

    types = ["TupleField", "SimpleDateField"]
    for type in types:
        try:
            execute(
                f"ALTER SEARCH INDEX SCHEMA ON {ks_name}.{raw_cf_name}"
                f" ADD types.fieldType[@name='{type}',"
                f" @class='com.datastax.bdp.search.solr.core.types.{type}'];"
            )
        except Exception as ex:
            _logger.warning(f"Maybe te field type {type} has been already" " defined in the schema. Cause: {ex}")
            pass

    types = ["TrieLongField", "TrieDoubleField", "TrieIntField", "BoolField", "UUIDField", "TrieDateField"]
    for type in types:
        # Define a TrieFloatField type to analyze texts (tokenizer, ascii, etc.)
        try:
            execute(
                f"ALTER SEARCH INDEX SCHEMA ON {ks_name}.{raw_cf_name}"
                f" ADD types.fieldType[@name='{type}',"
                f" @class='org.apache.solr.schema.{type}'];"
            )
        except Exception as ex:
            _logger.warning(f"Maybe te field type {type} has been already" " defined in the schema. Cause: {ex}")
            pass

    # Define a Point and LineString types for geospatial queries
    try:

        """
        <fieldType name="LocationField"
               class="solr.SpatialRecursivePrefixTreeFieldType"
               geo="false"
               worldBounds="ENVELOPE(-1000, 1000, 1000, -1000)"
               maxDistErr="0.001"
               units="degrees" />
               """
        execute(
            "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
            " ADD types.fieldType[@name='LocationField',"
            " @class='solr.SpatialRecursivePrefixTreeFieldType',"
            " @geo='false',"
            " @worldBounds='ENVELOPE(-1000, 1000, 1000, -1000)',"
            " @maxDistErr='0.001',"
            " @units='degrees'];".format(ks_name, raw_cf_name)
        )
    except Exception as ex:
        _logger.warning("Maybe te field type has been already" " defined in the schema. Cause: {}".format(ex))
        pass


def _define_location(ks_name, raw_cf_name, field_name):
    # Define a Point and LineString types for geospatial queries
    try:

        """
        <fieldType name="location"
            class="solr.LatLonType"
            subFieldSuffix="_coordinate"/>
        """
        execute(
            "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
            " ADD types.fieldType[@name='location',"
            " @class='solr.LatLonType',"
            " @subFieldSuffix='_coordinate'];".format(ks_name, raw_cf_name, field_name)
        )
        _process_field(ks_name, raw_cf_name, "coordinate", "tdouble", stored=False, dynamic=True)
    except Exception as ex:
        _logger.warning("Maybe te field type has been already" " defined in the schema. Cause: {}".format(ex))
        pass


def _process_copy_field(ks_name, table_name, src, dest, add=True):
    try:
        execute(
            "ALTER SEARCH INDEX SCHEMA ON {0}.{1} {2}"
            " copyField[@source='{3}', @dest='{4}'];".format(ks_name, table_name, "ADD" if add else "DROP", src, dest)
        )
    except Exception as ex:
        if add:
            _logger.warning("Maybe the copy field type has been already" " defined in the schema. Cause: {}".format(ex))
        else:
            _logger.warning("Maybe the copy field type is not avaiable " " in the schema. Cause: {}".format(ex))
        pass


def _process_field(
    ks_name,
    table_name,
    field_name,
    field_type="ISCStrField",
    indexed=True,
    stored=True,
    multivalued=False,
    docvalues=False,
    dynamic=False,
    add=True,
):
    try:
        if add:
            execute(
                "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
                " ADD fields.{2}[@name='{3}', @type='{4}',"
                " @indexed='{5}', @stored='{6}',"
                " @multiValued='{7}', @docValues='{8}'];".format(
                    ks_name,
                    table_name,
                    "field" if not dynamic else "dynamicField",
                    field_name if not dynamic else "*_{}".format(field_name),
                    field_type,
                    "true" if indexed else "false",
                    "true" if stored else "false",
                    "true" if multivalued else "false",
                    "true" if docvalues else "false",
                )
            )
        else:
            execute("ALTER SEARCH INDEX SCHEMA ON {0}.{1}" " DROP {2}".format(ks_name, table_name, field_name))
    except Exception as ex:
        if add:
            _logger.warning("Maybe te field has been already" " defined in the schema. Cause: {}".format(ex))
        else:
            _logger.warning("Maybe te field is not defined" " in the schema. Cause: {}".format(ex))
        pass


def create_index(model, index, keyspaces=None, connections=None):
    """
    Creates a new Search Index for the table indicated by the model,
    if it not exists.

    If `keyspaces` is specified, the index will be created for all
    specified keyspaces. Note that the `Model.__keyspace__` is
    ignored in that case.

    If `connections` is specified, the index will be synched for all
    specified connections. Note that the `Model.__connection__` is
    ignored in that case.
    If not specified, it will try to get the connection from the Model.


    **This function should be used with caution, especially in
    production environments.
    Take care to execute schema modifications in a single context
    (i.e. not concurrently with other clients).**

    *There are plans to guard schema-modifying functions with an
    environment-driven conditional.*
    """

    context = management._get_context(keyspaces, connections)
    for connection, keyspace in context:
        with query.ContextQuery(model, keyspace=keyspace) as m:
            _create_index(m, index, connection=connection)


def _find_udt_attribute(model, field_name):
    field_segments = field_name.split(".")
    _logger.debug("[UDT] Field segments: [{}]".format(field_segments))
    if len(field_segments) > 1:
        attribute = getattr(model, field_segments[0], None)
        clazz = attribute.column.__class__

        if attribute.column.__class__ == columns.UserDefinedType:
            clazz = attribute.column.user_type

        if issubclass(clazz, (columns.List, columns.Set)):
            if attribute.column.types[0].__class__ == columns.UserDefinedType:
                clazz = attribute.column.types[0].user_type
            else:
                clazz = attribute.column.types[0].__class__
        _logger.debug("[UDT] Model for field [{}]: {}".format(field_segments[0], clazz))
        return _find_udt_attribute(clazz, ".".join(field_segments[1:]))

    return getattr(model, field_segments[0], None)


def _drop_unnecessary_indexes(ks_name, table_name, fieldsname):
    for fieldname in fieldsname:
        try:
            execute(f"ALTER SEARCH INDEX SCHEMA ON {ks_name}.{table_name} DROP field {fieldname}")
        except Exception as ex:
            _logger.warning(f"Unable to remove unnecessary field {fieldname}. Cause: {ex}")


def _get_solr_type(model, index, search_field):
    try:
        if "." not in search_field.model_attr:
            attribute = getattr(model, search_field.model_attr, None)
        else:
            _logger.debug("Find field [{}] in UDT object.".format(search_field.model_attr))
            attribute = _find_udt_attribute(model, search_field.model_attr)

        _logger.debug("Attribute for [{}]: {}".format(search_field.model_attr, attribute))

        if attribute:
            clazz = attribute.column.__class__
            if issubclass(clazz, columns.List):
                clazz = attribute.column.types[0].__class__
            elif issubclass(clazz, columns.Set):
                clazz = attribute.column.types[0].__class__

            if issubclass(clazz, columns.BigInt):
                return "TrieLongField"
            elif (
                issubclass(clazz, columns.Integer)
                or (issubclass(clazz, columns.SmallInt))
                or (issubclass(clazz, columns.Counter))
                or (issubclass(clazz, columns.VarInt))
            ):
                return "TrieIntField"
            elif issubclass(clazz, columns.Double):
                return "TrieDoubleField"
            elif issubclass(clazz, columns.Float):
                return "TrieFloatField"
            elif issubclass(clazz, columns.Decimal):
                return "TrieDecimalField"
            elif issubclass(clazz, columns.Date):
                return "SimpleDateField"
            elif issubclass(clazz, columns.DateTime):
                return "TrieDateField"
            elif issubclass(clazz, columns.Time):
                return "TrieDateField"
            elif issubclass(clazz, columns.Boolean):
                return "BoolField"
            elif issubclass(clazz, columns.TimeUUID):
                return "TimeUUIDField"
            elif issubclass(clazz, columns.UUID):
                return "UUIDField"

        if issubclass(search_field.__class__, fields.LocationField):
            return "LocationField"

        if (search_field.model_attr in index.Meta.text_fields and not search_field.faceted) or (
            isinstance(search_field, TextField)
        ):
            return "TextField"

        if (
            attribute.column.primary_key
            or attribute.column.partition_key
            or search_field.faceted
            or (hasattr(attribute.column, "unique") and attribute.column.unique)
        ):
            return "StrField"

        _logger.debug("ISCStrField for field: {}".format(search_field.model_attr))
        return "ISCStrField"
    except Exception as ex:
        _logger.error(f"Unable to process index field [{search_field.index_fieldname}] of model {model}. Cause: {ex}")
        raise ex


# def _extra_create_search_index_params(model, exclude_fields):


def _create_index(model, index, connection=None):
    if not management._allow_schema_modification():
        return

    connection = connection or model._get_connection()

    # don't try to create indexes in non existant tables
    meta = management.get_cluster(connection).metadata

    ks_name = model._get_keyspace()
    raw_cf_name = model._raw_column_family_name()

    try:
        _logger.info("Creating SEARCH INDEX if not exists for model: {}".format(model))

        extra_params = ""
        if hasattr(index.Meta, "exclude") and len(index.Meta.exclude) > 0:
            field_names = [
                f'"{name}"'
                for name, value in inspect.getmembers(model, lambda a: isinstance(a, models.ColumnQueryEvaluator))
                if name not in index.Meta.exclude + ["pk"]
            ]
            extra_params = f' WITH COLUMNS {",".join(field_names)}'

        # meta.keyspaces[ks_name].tables[raw_cf_name]
        # primary_keys = model._primary_keys.keys()
        #  WITH OPTIONS {{ lenient:true }}
        print("CREATE SEARCH INDEX IF NOT EXISTS ON {0}.{1}{2};".format(ks_name, raw_cf_name, extra_params))
        execute(
            "CREATE SEARCH INDEX IF NOT EXISTS ON {0}.{1}{2};".format(ks_name, raw_cf_name, extra_params), timeout=30.0
        )

        if hasattr(index.Meta, "index_settings"):
            for param, value in index.Meta.index_settings.items():
                _logger.info("Setting index parameters: {0} = {1}".format(param, value))
                execute(
                    "ALTER SEARCH INDEX CONFIG ON {0}.{1}" " SET {2} = {3};".format(ks_name, raw_cf_name, param, value)
                )

        _define_types(ks_name, raw_cf_name)

        search_fields = [
            attr
            for attr in index.__class__.__dict__["fields"].values()
            if issubclass(attr.__class__, fields.SearchField)
        ]

        # if hasattr(index.Meta, "exclude") and len(index.Meta.exclude) > 0:
        #    _drop_unnecessary_indexes(ks_name, raw_cf_name, index.Meta.exclude)

        document_fields = []

        for search_field in search_fields:

            # If the field do not have a direct mapping with the model
            if not search_field.model_attr:
                continue

            _logger.info("Processing field field {0}({1})".format(search_field.__class__, search_field.model_attr))

            # force the creation of the field if it does not exists yet (the
            #   original table has been changed after the index was created
            try:
                _process_field(
                    ks_name,
                    raw_cf_name,
                    search_field.model_attr,
                    field_type=_get_solr_type(model, index, search_field),
                    multivalued=search_field.is_multivalued,
                    stored=True,
                    indexed=True,
                    docvalues=False,
                )
            except Exception as ex:
                _logger.warning("Maybe te field has been already" " created in the schema. Cause: {}".format(ex))

            # https://docs.datastax.com/en/
            # datastax_enterprise/5.0/
            # datastax_enterprise/srch/queriesGeoSpatial.html
            # <fieldType name="location" class="solr.LatLonType"
            #  subFieldSuffix="_coordinate"/>
            if issubclass(search_field.__class__, fields.LocationField):
                execute(
                    "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
                    " SET fields.field[@name='{2}']@type='LocationField';".format(
                        ks_name, raw_cf_name, search_field.model_attr
                    )
                )

                continue

            # Facet fields
            if search_field.faceted:
                # We need to create a <field>_exact field in Solr with
                #  docValues=true and that will receive the data from
                #  the original <field> (copyFrom)
                # This <field>_exact field is the one used by Hasystak to
                #  do the facet queries
                _process_field(
                    ks_name,
                    raw_cf_name,
                    "{}_exact".format(search_field.model_attr),
                    field_type=_get_solr_type(model, index, search_field),
                    multivalued=search_field.is_multivalued,
                    stored=False,
                    docvalues=True,
                )

                _process_copy_field(
                    ks_name, raw_cf_name, search_field.model_attr, "{}_exact".format(search_field.model_attr)
                )

            # Get a reference to the model column definition
            attribute = getattr(model, search_field.model_attr, None)

            # Indexed field?
            if not (attribute and isinstance(attribute.column, columns.Map)) and not (
                attribute
                and hasattr(attribute.column, "value_col")
                and (isinstance(attribute.column.value_col, columns.UserDefinedType))
            ):
                execute(
                    "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
                    " SET fields.field[@name='{2}']@type='{3}';".format(
                        ks_name, raw_cf_name, search_field.model_attr, _get_solr_type(model, index, search_field)
                    )
                )
                if search_field.indexed:
                    execute(
                        "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
                        " SET fields.field[@name='{2}']@indexed='true';".format(
                            ks_name, raw_cf_name, search_field.model_attr
                        )
                    )
                else:
                    execute(
                        "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
                        " SET fields.field[@name='{2}']@indexed='false';".format(
                            ks_name, raw_cf_name, search_field.model_attr
                        )
                    )

            # Facet field?: force docValues=true
            if not (attribute and isinstance(attribute.column, columns.Map)) and not (
                attribute
                and hasattr(attribute.column, "value_col")
                and (isinstance(attribute.column.value_col, columns.UserDefinedType))
            ):
                if search_field.is_multivalued:
                    execute(
                        "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
                        " SET fields.field[@name='{2}']@multiValued='true';".format(
                            ks_name, raw_cf_name, search_field.model_attr
                        )
                    )
                else:
                    execute(
                        "ALTER SEARCH INDEX SCHEMA ON {0}.{1}"
                        " SET fields.field[@name='{2}']@multiValued='false';".format(
                            ks_name, raw_cf_name, search_field.model_attr
                        )
                    )

            # All the document fields have to be TextFields to be
            # processed as tokens
            if not (attribute and isinstance(attribute.column, columns.Map)) and not (
                attribute
                and hasattr(attribute.column, "value_col")
                and (isinstance(attribute.column.value_col, columns.UserDefinedType))
            ):
                if issubclass(search_field.__class__, (fields.CharField, TextField)):
                    # if search_field.model_attr in index.Meta.text_fields:
                    if search_field.model_attr in index.Meta.text_fields and not search_field.faceted:
                        _logger.info("Changing SEARCH INDEX field {0} to TextField".format(search_field.model_attr))
                        execute(
                            "ALTER SEARCH INDEX SCHEMA ON {0}.{1} "
                            " SET fields.field[@name='{2}']@type='TextField';".format(
                                ks_name, raw_cf_name, search_field.model_attr
                            )
                        )

                    document_fields.append(search_field)
                    # else:
                    #    execute(
                    #        "ALTER SEARCH INDEX SCHEMA ON {0}.{1} "
                    #        " SET fields.field[@name='{2}']@type='ISCStrField';".
                    #        format(
                    #            ks_name,
                    #            raw_cf_name,
                    #            search_field.model_attr))

        # If there are document fields we need to copy all them into
        # the text field
        if len(document_fields):
            _process_field(ks_name, raw_cf_name, "text", field_type="TextField", stored=False, multivalued=True)

            for document_field in document_fields:
                _process_copy_field(ks_name, raw_cf_name, document_field.model_attr, "text")

        # Reload the index for the changes to take effect
        execute("RELOAD SEARCH INDEX ON {0}.{1};".format(ks_name, raw_cf_name), timeout=30)

    except KeyError:
        _logger.exception("Unable to create the search index")
        pass


def sync(alias, only_model=None):
    engine = get_engine_from_db_alias(alias)

    if engine != "django_cassandra_engine":
        raise CommandError("Database {} is not cassandra!".format(alias))

    connection = connections[alias]
    connection.connect()
    keyspace = connection.settings_dict["NAME"]

    _logger.info("Creating indexes in {} [CONNECTION {}] ..".format(keyspace, alias))

    connection.connection.cluster.refresh_schema_metadata()
    connection.connection.cluster.schema_metadata_enabled = True

    indexes_by_model = UnifiedIndex().get_indexes()

    for app_name, app_models in connection.introspection.cql_models.items():
        for model in app_models:
            # If the app model is registered as a SearchIndex
            if model in indexes_by_model:
                model_name = "{0}.{1}".format(model.__module__, model.__name__)
                if not only_model or model_name == only_model:
                    _logger.info("Creating index %s.%s".format(app_name, model.__name__))
                    _logger.info(
                        "Index class associated to te model {0}.{1}".format(
                            app_name, indexes_by_model.get(model).__class__.__name__
                        )
                    )
                    create_index(model, indexes_by_model.get(model))


class Command(BaseCommand):
    help = "Sync Cassandra Index(es)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--database", action="store", dest="database", default=None, help="Nominates a database to synchronize.",
        )
        parser.add_argument(
            "--model",
            action="store",
            dest="model",
            default=None,
            help="The name of the model class we" " want to generate the indexes.",
        )

    def handle(self, **options):

        model = options.get("model")

        database = options.get("database")
        if database is not None:
            return sync(database, model)

        cassandra_alias = None
        for alias in connections:
            engine = get_engine_from_db_alias(alias)
            if engine == "django_cassandra_engine":
                sync(alias, model)
                cassandra_alias = alias

        if cassandra_alias is None:
            raise CommandError("Please add django_cassandra_engine backend to DATABASES!")
