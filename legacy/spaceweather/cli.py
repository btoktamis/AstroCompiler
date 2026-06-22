import argparse
import sys
import os
from spaceweather.engine import SpaceWeatherCompiler
from spaceweather.eop_engine import EOPCompiler

def main():
    parser = argparse.ArgumentParser(
        description="Offline Space Weather Compiler: Aggregates space weather datasets "
                    "from primary feeds (GFZ, SIDC, Penticton, NOAA, NASA) and compiles them."
    )
    
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Execute the compilation pipeline and write files."
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="SW-All.txt",
        help="Output file path (default: SW-All.txt)."
    )
    
    parser.add_argument(
        "--format",
        choices=["txt", "csv"],
        default="txt",
        help="Output file format (txt or csv, default: txt)."
    )
    
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Fetch official Celestrak database and verify compatibility with compiled output."
    )
    
    parser.add_argument(
        "--cache-dir",
        type=str,
        default="./cache",
        help="Directory to cache downloaded raw files (default: ./cache)."
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed processing logs."
    )
    
    # EOP Arguments
    parser.add_argument(
        "--compile-eop",
        action="store_true",
        help="Execute the EOP compilation pipeline."
    )
    parser.add_argument(
        "--eop-output",
        type=str,
        default="C:/Users/baris/Desktop/90-tool/05_TKS_Conj_Auto/Inputs/AppData/eop19620101.txt",
        help="EOP output file path."
    )
    parser.add_argument(
        "--eop-format",
        choices=["txt", "csv"],
        default="txt",
        help="EOP output file format (txt or csv, default: txt)."
    )
    parser.add_argument(
        "--eop-legacy",
        action="store_true",
        help="Include NGA coefficients block (legacy format)."
    )

    parser.add_argument(
        "--verify-eop",
        action="store_true",
        help="Compare compiled/existing EOP output with live Celestrak database."
    )
    parser.add_argument(
        "--eop-online",
        action="store_true",
        help="Use Celestrak directly to download base data instead of compiling from USNO/IERS raw feeds."
    )
    
    args = parser.parse_args()
    
    # Check if any action is requested
    if not args.compile and not args.verify and not args.compile_eop and not args.verify_eop:
        parser.print_help()
        sys.exit(0)
        
    # Set up verbose log callback
    def log_callback(msg):
        if args.verbose or args.verify or args.verify_eop:
            print(msg)
            
    # Process Space Weather action
    if args.compile or args.verify:
        compiler = SpaceWeatherCompiler(cache_dir=args.cache_dir, log_callback=log_callback)
        data = None
        try:
            data = compiler.compile()
        except Exception as e:
            print(f"Error executing Space Weather compilation pipeline: {e}", file=sys.stderr)
            sys.exit(1)
            
        if args.compile:
            try:
                if args.format == "txt":
                    compiler.write_to_legacy_txt(data, args.output)
                elif args.format == "csv":
                    compiler.write_to_csv(data, args.output)
                print(f"Space Weather compilation successful! Saved file to {args.output}")
            except Exception as e:
                print(f"Error saving Space Weather output file: {e}", file=sys.stderr)
                sys.exit(1)
                
        if args.verify:
            temp_output = os.path.join(args.cache_dir, "temp_compile_for_verify.txt")
            try:
                compiler.write_to_legacy_txt(data, temp_output)
                report = compiler.verify_with_celestrak(temp_output)
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                if report["obs_match_rate"] >= 0.98:
                    print("Space Weather verification PASSED! Core compatibility is high.")
                else:
                    print("Space Weather verification FAILED! Discrepancies exceed threshold.", file=sys.stderr)
                    sys.exit(2)
            except Exception as e:
                print(f"Error during Space Weather verification: {e}", file=sys.stderr)
                sys.exit(1)

    # Process EOP actions
    if args.compile_eop or args.verify_eop:
        eop_compiler = EOPCompiler(cache_dir=args.cache_dir, log_callback=log_callback)
        
        if args.compile_eop:
            try:
                # If eop_online is True, we compile with offline_mode=False
                data = eop_compiler.compile(offline_mode=not args.eop_online)
                if args.eop_format == "txt":
                    eop_compiler.write_to_legacy_txt(
                        data, args.eop_output, 
                        legacy_mode=args.eop_legacy
                    )
                else:
                    eop_compiler.write_to_csv(data, args.eop_output)
                print(f"EOP Compilation successful! Saved file to {args.eop_output}")
            except Exception as e:
                print(f"Error compiling EOP: {e}", file=sys.stderr)
                sys.exit(1)
                
        if args.verify_eop:
            try:
                report = eop_compiler.verify_with_celestrak(args.eop_output)
                if report["obs_match_rate"] >= 0.98:
                    print("EOP Verification PASSED! Core compatibility is high.")
                    sys.exit(0)
                else:
                    print("EOP Verification FAILED! Discrepancies exceed threshold.", file=sys.stderr)
                    sys.exit(2)
            except Exception as e:
                print(f"Error during EOP verification: {e}", file=sys.stderr)
                sys.exit(1)

if __name__ == "__main__":
    main()
