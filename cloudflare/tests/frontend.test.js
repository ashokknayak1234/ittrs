import {test} from 'node:test';
import assert from 'node:assert/strict';
import {filterTickets,flag} from '../public/view-model.js';

test('queue filters combine search with severity, PostgreSQL flags, and local SQLite flags',()=>{
  const tickets=[{id:'first',complaint_text:'VPN unavailable',team:'Team Beta',severity:'Critical',sla_alerted:true,satisfaction_status:'Not_Satisfied'},
    {id:'second',complaint_text:'Laptop issue',team:'Team Alpha',severity:'High',sla_alerted:1},
    {id:'third',complaint_text:null,team:'Team Beta',severity:'Low',sla_alerted:false}];
  assert.deepEqual(filterTickets(tickets,' vpn ','Critical').map(t=>t.id),['first']);
  assert.equal(filterTickets(tickets,'','alerts').length,2);
  assert.equal(filterTickets(tickets,'','unsatisfied').length,1);
  assert.equal(filterTickets(tickets,'beta','all').length,2);
  assert.equal(filterTickets(tickets,'vpn','Low').length,0);
  assert.equal(flag('false'),false);
});
