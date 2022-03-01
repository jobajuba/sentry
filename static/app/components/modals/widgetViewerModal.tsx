import * as React from 'react';
import {withRouter, WithRouterProps} from 'react-router';
import {css} from '@emotion/react';
import styled from '@emotion/styled';
import cloneDeep from 'lodash/cloneDeep';

import {ModalRenderProps} from 'sentry/actionCreators/modal';
import Button from 'sentry/components/button';
import ButtonBar from 'sentry/components/buttonBar';
import GridEditable, {GridColumnOrder} from 'sentry/components/gridEditable';
import Tooltip from 'sentry/components/tooltip';
import {t} from 'sentry/locale';
import space from 'sentry/styles/space';
import {Organization, PageFilters} from 'sentry/types';
import useApi from 'sentry/utils/useApi';
import withPageFilters from 'sentry/utils/withPageFilters';
import {DisplayType, Widget, WidgetType} from 'sentry/views/dashboardsV2/types';
import {
  eventViewFromWidget,
  getFieldsFromEquations,
  getWidgetDiscoverUrl,
  getWidgetIssueUrl,
} from 'sentry/views/dashboardsV2/utils';
import IssueWidgetQueries from 'sentry/views/dashboardsV2/widgetCard/issueWidgetQueries';
import WidgetCardChartContainer from 'sentry/views/dashboardsV2/widgetCard/widgetCardChartContainer';
import WidgetQueries from 'sentry/views/dashboardsV2/widgetCard/widgetQueries';

import {
  renderGridBodyCell,
  renderGridHeaderCell,
} from './widgetViewerModal/widgetViewerTableCell';

export type WidgetViewerModalOptions = {
  organization: Organization;
  widget: Widget;
  onEdit?: () => void;
};

type Props = ModalRenderProps &
  WithRouterProps &
  WidgetViewerModalOptions & {
    organization: Organization;
    selection: PageFilters;
  };

const FULL_TABLE_ITEM_LIMIT = 20;
const HALF_TABLE_ITEM_LIMIT = 10;
const GEO_COUNTRY_CODE = 'geo.country_code';

function WidgetViewerModal(props: Props) {
  const {organization, widget, selection, location, Footer, Body, Header, onEdit} = props;
  const isTableWidget = widget.displayType === DisplayType.TABLE;
  const renderWidgetViewer = () => {
    const api = useApi();

    // Create Table widget
    const tableWidget = {...cloneDeep(widget), displayType: DisplayType.TABLE};
    const fields = tableWidget.queries[0].fields;

    // World Map view should always have geo.country in the table chart
    if (
      widget.displayType === DisplayType.WORLD_MAP &&
      !fields.includes(GEO_COUNTRY_CODE)
    ) {
      fields.unshift(GEO_COUNTRY_CODE);
    }
    if (!isTableWidget) {
      // Updates fields by adding any individual terms from equation fields as a column
      const equationFields = getFieldsFromEquations(fields);
      equationFields.forEach(term => {
        if (Array.isArray(fields) && !fields.includes(term)) {
          fields.unshift(term);
        }
      });
    }
    const eventView = eventViewFromWidget(
      tableWidget.title,
      tableWidget.queries[0],
      selection,
      tableWidget.displayType
    );
    const columnOrder = eventView.getColumns();
    const columnSortBy = eventView.getSorts();
    return (
      <React.Fragment>
        {widget.displayType !== DisplayType.TABLE && (
          <Container>
            <WidgetCardChartContainer
              api={api}
              organization={organization}
              selection={selection}
              widget={widget}
            />
          </Container>
        )}
        <TableContainer>
          {widget.widgetType === WidgetType.ISSUE ? (
            <IssueWidgetQueries
              api={api}
              organization={organization}
              widget={tableWidget}
              selection={selection}
              limit={
                widget.displayType === DisplayType.TABLE
                  ? FULL_TABLE_ITEM_LIMIT
                  : HALF_TABLE_ITEM_LIMIT
              }
            >
              {({transformedResults, loading}) => {
                return (
                  <GridEditable
                    isLoading={loading}
                    data={transformedResults}
                    columnOrder={columnOrder}
                    columnSortBy={columnSortBy}
                    grid={{
                      renderHeadCell: renderGridHeaderCell({
                        ...props,
                      }) as (
                        column: GridColumnOrder,
                        columnIndex: number
                      ) => React.ReactNode,
                      renderBodyCell: renderGridBodyCell({
                        ...props,
                      }),
                    }}
                    location={location}
                  />
                );
              }}
            </IssueWidgetQueries>
          ) : (
            <WidgetQueries
              api={api}
              organization={organization}
              widget={tableWidget}
              selection={selection}
              limit={
                widget.displayType === DisplayType.TABLE
                  ? FULL_TABLE_ITEM_LIMIT
                  : HALF_TABLE_ITEM_LIMIT
              }
            >
              {({tableResults, loading}) => {
                return (
                  <GridEditable
                    isLoading={loading}
                    data={tableResults?.[0]?.data ?? []}
                    columnOrder={columnOrder}
                    columnSortBy={columnSortBy}
                    grid={{
                      renderHeadCell: renderGridHeaderCell({
                        ...props,
                        tableData: tableResults?.[0],
                      }) as (
                        column: GridColumnOrder,
                        columnIndex: number
                      ) => React.ReactNode,
                      renderBodyCell: renderGridBodyCell({
                        ...props,
                        tableData: tableResults?.[0],
                      }),
                    }}
                    location={location}
                  />
                );
              }}
            </WidgetQueries>
          )}
        </TableContainer>
      </React.Fragment>
    );
  };

  const StyledHeader = styled(Header)`
    ${headerCss}
  `;
  const StyledFooter = styled(Footer)`
    ${footerCss}
  `;

  let openLabel: string;
  let path: string;
  switch (widget.widgetType) {
    case WidgetType.ISSUE:
      openLabel = t('Open in Issues');
      path = getWidgetIssueUrl(widget, selection, organization);
      break;
    case WidgetType.DISCOVER:
    default:
      openLabel = t('Open in Discover');
      path = getWidgetDiscoverUrl(widget, selection, organization);
      break;
  }
  return (
    <React.Fragment>
      <StyledHeader closeButton>
        <Tooltip title={widget.title} showOnlyOnOverflow>
          <WidgetTitle>{widget.title}</WidgetTitle>
        </Tooltip>
      </StyledHeader>
      <Body>{renderWidgetViewer()}</Body>
      <StyledFooter>
        <ButtonBar gap={1}>
          <Button type="button" onClick={onEdit}>
            {t('Edit Widget')}
          </Button>
          <Button to={path} priority="primary" type="button">
            {openLabel}
          </Button>
        </ButtonBar>
      </StyledFooter>
    </React.Fragment>
  );
}

export const modalCss = css`
  width: 100%;
  max-width: 1400px;
`;

const headerCss = css`
  margin: -${space(4)} -${space(4)} 0px -${space(4)};
`;
const footerCss = css`
  margin: 0px -${space(4)} -${space(4)};
`;

const Container = styled('div')`
  height: 300px;
  max-height: 300px;
  position: relative;

  & > div {
    padding: 20px 0px;
  }
`;

// Table Container allows Table display to work around parent padding and fill full modal width
const TableContainer = styled('div')`
  max-width: 1400px;
  position: relative;
  margin: ${space(4)} 0;
  & > div {
    margin: 0;
  }

  & td:first-child {
    padding: ${space(1)} ${space(2)};
  }
`;

const WidgetTitle = styled('h4')`
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow: hidden;
`;

export default withRouter(withPageFilters(WidgetViewerModal));