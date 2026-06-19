export namespace eop {
	
	export class EOPRecord {
	    year: number;
	    month: number;
	    day: number;
	    mjd: number;
	    x: number;
	    y: number;
	    ut1_utc: number;
	    lod: number;
	    dpsi: number;
	    deps: number;
	    dx: number;
	    dy: number;
	    dat: number;
	
	    static createFrom(source: any = {}) {
	        return new EOPRecord(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.year = source["year"];
	        this.month = source["month"];
	        this.day = source["day"];
	        this.mjd = source["mjd"];
	        this.x = source["x"];
	        this.y = source["y"];
	        this.ut1_utc = source["ut1_utc"];
	        this.lod = source["lod"];
	        this.dpsi = source["dpsi"];
	        this.deps = source["deps"];
	        this.dx = source["dx"];
	        this.dy = source["dy"];
	        this.dat = source["dat"];
	    }
	}

}

export namespace spaceweather {
	
	export class Record {
	    date: string;
	    year: number;
	    month: number;
	    day: number;
	    bsrn: number;
	    nd: number;
	    kp_vals: number[];
	    ap_vals: number[];
	    ap_avg: number;
	    isn: number;
	    f107_obs: number;
	    f107_adj: number;
	    f107_obs_ctr: number;
	    f107_obs_last: number;
	    f107_adj_ctr: number;
	    f107_adj_last: number;
	    q_flag: number;
	    source: string;
	
	    static createFrom(source: any = {}) {
	        return new Record(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.date = source["date"];
	        this.year = source["year"];
	        this.month = source["month"];
	        this.day = source["day"];
	        this.bsrn = source["bsrn"];
	        this.nd = source["nd"];
	        this.kp_vals = source["kp_vals"];
	        this.ap_vals = source["ap_vals"];
	        this.ap_avg = source["ap_avg"];
	        this.isn = source["isn"];
	        this.f107_obs = source["f107_obs"];
	        this.f107_adj = source["f107_adj"];
	        this.f107_obs_ctr = source["f107_obs_ctr"];
	        this.f107_obs_last = source["f107_obs_last"];
	        this.f107_adj_ctr = source["f107_adj_ctr"];
	        this.f107_adj_last = source["f107_adj_last"];
	        this.q_flag = source["q_flag"];
	        this.source = source["source"];
	    }
	}

}

